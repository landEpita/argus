"""
HTTP port and its httpx adapter.

Adapters depend on the :class:`HttpClient` protocol, never on httpx directly,
so they can be tested with a stub. The adapter translates transport failures
into the provider error hierarchy, which is what drives fallback, and caps
response sizes so one misbehaving upstream cannot exhaust memory.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from argus.providers.errors import (
    ProviderNotFoundError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)

_RETRYABLE_STATUS = frozenset({408, 425})
# Standard header first, then the non-standard ones seen in the wild (OpenSky).
_RETRY_AFTER_HEADERS = ("retry-after", "x-rate-limit-retry-after-seconds")
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


class HttpClient(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> Any: ...

    async def get_bytes(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout_s: float | None = None,
    ) -> bytes: ...

    async def post_form(
        self,
        url: str,
        *,
        provider: str,
        data: Mapping[str, str],
        timeout_s: float | None = None,
    ) -> Any: ...

    async def aclose(self) -> None: ...


class HttpxClient:
    def __init__(
        self,
        timeout_s: float = 10.0,
        user_agent: str = "argus/0.1 (+https://github.com/)",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            transport=transport,
        )

    async def get_json(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> Any:
        merged = {"Accept": "application/json", **(headers or {})}
        body = await self.get_bytes(
            url, provider=provider, params=params, headers=merged, timeout_s=timeout_s
        )
        try:
            return json.loads(body)
        except ValueError as exc:
            raise ProviderResponseError(provider, "invalid JSON") from exc

    async def get_bytes(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout_s: float | None = None,
    ) -> bytes:
        """``timeout_s`` overrides the client default for slow-but-healthy upstreams."""
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else httpx.Timeout(timeout_s)
        try:
            async with self._client.stream(
                "GET", url, params=params, headers=headers, timeout=timeout
            ) as response:
                _check_status(provider, response.status_code, response.headers)
                declared = response.headers.get("content-length")
                if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                    raise ProviderResponseError(provider, f"response larger than {max_bytes} bytes")
                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > max_bytes:
                        raise ProviderResponseError(
                            provider, f"response larger than {max_bytes} bytes"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(provider, "timeout") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(
                provider, f"transport error: {type(exc).__name__}"
            ) from exc

    async def post_form(
        self,
        url: str,
        *,
        provider: str,
        data: Mapping[str, str],
        timeout_s: float | None = None,
    ) -> Any:
        """Form-encoded POST returning JSON (OAuth token endpoints)."""
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else httpx.Timeout(timeout_s)
        try:
            response = await self._client.post(url, data=dict(data), timeout=timeout)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(provider, "timeout") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(
                provider, f"transport error: {type(exc).__name__}"
            ) from exc
        _check_status(provider, response.status_code, response.headers)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderResponseError(provider, "invalid JSON") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for name in _RETRY_AFTER_HEADERS:
        value = headers.get(name)
        if value is not None:
            try:
                return max(0.0, float(value))
            except ValueError:
                continue  # an HTTP-date; rare enough to ignore
    return None


def _check_status(provider: str, status: int, headers: Mapping[str, str] | None = None) -> None:
    if status == 429:
        raise ProviderRateLimitedError(provider, "HTTP 429", _retry_after(headers or {}))
    if status >= 500 or status in _RETRYABLE_STATUS:
        raise ProviderUnavailableError(provider, f"HTTP {status}")
    if status == 404:
        raise ProviderNotFoundError(provider, "HTTP 404")
    if status >= 400:
        raise ProviderResponseError(provider, f"HTTP {status}")
