from collections.abc import AsyncIterator

import httpx
import pytest

from argus.infra.http import HttpxClient
from argus.providers.errors import (
    ProviderNotFoundError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)


def client_returning(handler: httpx.MockTransport) -> HttpxClient:
    return HttpxClient(transport=handler)


async def test_returns_decoded_json_and_forwards_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = client_returning(httpx.MockTransport(handler))
    assert await client.get_json("https://x.test/a", provider="x", params={"q": "1"}) == {
        "ok": True
    }
    assert seen[0].url.params["q"] == "1"
    assert seen[0].headers["User-Agent"].startswith("argus/")
    await client.aclose()


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_retryable_status_is_unavailable(status: int) -> None:
    client = client_returning(httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(ProviderUnavailableError, match=f"HTTP {status}"):
        await client.get_json("https://x.test", provider="x")


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_client_error_is_a_response_error(status: int) -> None:
    client = client_returning(httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(ProviderResponseError, match=f"HTTP {status}"):
        await client.get_json("https://x.test", provider="x")


async def test_invalid_json_is_a_response_error() -> None:
    client = client_returning(httpx.MockTransport(lambda _: httpx.Response(200, text="<html>")))
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        await client.get_json("https://x.test", provider="x")


async def test_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = client_returning(httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError, match="timeout") as info:
        await client.get_json("https://x.test", provider="opensky")
    assert info.value.provider == "opensky"


async def test_connection_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = client_returning(httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError, match="ConnectError"):
        await client.get_json("https://x.test", provider="x")


async def test_get_bytes_returns_raw_body() -> None:
    client = client_returning(
        httpx.MockTransport(lambda _: httpx.Response(200, content=b"a,b\n1,2"))
    )
    assert await client.get_bytes("https://x.test", provider="x") == b"a,b\n1,2"


async def test_declared_oversize_is_refused() -> None:
    client = client_returning(
        httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-length": "999"}, content=b"x")
        )
    )
    with pytest.raises(ProviderResponseError, match="larger than 10 bytes"):
        await client.get_bytes("https://x.test", provider="x", max_bytes=10)


async def test_streamed_oversize_is_refused() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * 6
        yield b"x" * 6

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())

    client = client_returning(httpx.MockTransport(handler))
    with pytest.raises(ProviderResponseError, match="larger than 10 bytes"):
        await client.get_bytes("https://x.test", provider="x", max_bytes=10)


async def test_per_request_timeout_overrides_the_default() -> None:
    seen: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={})

    client = HttpxClient(timeout_s=10, transport=httpx.MockTransport(handler))
    await client.get_json("https://x.test", provider="x")
    await client.get_json("https://x.test", provider="x", timeout_s=45)
    assert seen[0]["read"] == 10
    assert seen[1]["read"] == 45


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "30"}, 30.0),
        ({"X-Rate-Limit-Retry-After-Seconds": "78121"}, 78121.0),
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({}, None),
    ],
)
async def test_429_carries_the_retry_hint(headers: dict[str, str], expected: float | None) -> None:
    client = client_returning(httpx.MockTransport(lambda _: httpx.Response(429, headers=headers)))
    with pytest.raises(ProviderRateLimitedError) as info:
        await client.get_json("https://x.test", provider="opensky")
    assert info.value.retry_after_s == expected


async def test_404_is_not_found() -> None:
    client = client_returning(httpx.MockTransport(lambda _: httpx.Response(404)))
    with pytest.raises(ProviderNotFoundError):
        await client.get_json("https://x.test", provider="x")


async def test_post_form() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "t"})

    client = client_returning(httpx.MockTransport(handler))
    assert await client.post_form("https://x.test/token", provider="x", data={"a": "1"}) == {
        "access_token": "t"
    }
    assert seen[0].method == "POST"
    assert seen[0].content == b"a=1"


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401), ProviderResponseError),
        (httpx.Response(200, text="nope"), ProviderResponseError),
        (httpx.Response(503), ProviderUnavailableError),
    ],
)
async def test_post_form_errors(response: httpx.Response, error: type[Exception]) -> None:
    client = client_returning(httpx.MockTransport(lambda _: response))
    with pytest.raises(error):
        await client.post_form("https://x.test", provider="x", data={})


async def test_post_form_transport_errors() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no", request=request)

    for handler, match in ((timeout, "timeout"), (refused, "ConnectError")):
        client = client_returning(httpx.MockTransport(handler))
        with pytest.raises(ProviderUnavailableError, match=match):
            await client.post_form("https://x.test", provider="x", data={})
