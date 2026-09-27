"""
Web Push (VAPID): alerts reach the browser even when Argus is closed.

The server's VAPID key pair is generated once and kept in the database; the
browser subscribes with its public half. Push services (FCM, Mozilla, Apple)
only relay an encrypted payload they cannot read.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01, b64urlencode

from argus.domain.alerts import Alert, Channel
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError

KEY_NAME = "vapid_private_pem"
TIMEOUT_S = 10.0

PushFn = Callable[..., Any]


class SecretStore(Protocol):
    async def get(self, name: str) -> str | None: ...
    async def put(self, name: str, value: str) -> None: ...


def public_key_of(private_pem: str) -> str:
    """The applicationServerKey a browser subscribes with (uncompressed P-256, base64url)."""
    vapid = Vapid01.from_pem(private_pem.encode())
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return str(b64urlencode(raw))


class VapidKeys:
    """Generated on first use, then read back: subscriptions survive restarts."""

    def __init__(self, store: SecretStore) -> None:
        self._store = store
        self._pem: str | None = None
        self._lock = asyncio.Lock()

    async def private_pem(self) -> str:
        async with self._lock:
            if self._pem is None:
                pem = await self._store.get(KEY_NAME)
                if pem is None:
                    vapid = Vapid01()
                    vapid.generate_keys()
                    pem = vapid.private_pem().decode()
                    await self._store.put(KEY_NAME, pem)
                self._pem = pem
            return self._pem

    async def public_key(self) -> str:
        return public_key_of(await self.private_pem())


def payload_of(alert: Alert) -> str:
    """What the service worker shows. Small on purpose: push payloads are limited to 4 KB."""
    return json.dumps(
        {
            "title": alert.title[:120],
            "body": f"{alert.rule_name} · {alert.source}"[:200],
            "tag": alert.id,
            "url": "/#map" if alert.lat is not None else "/#watch",
            "severity": alert.severity.value,
        }
    )


class WebPushNotifier:
    def __init__(self, keys: VapidKeys, subject: str, push: PushFn | None = None) -> None:
        self._keys = keys
        self._subject = subject
        self._push = push

    async def send(self, channel: Channel, alert: Alert) -> None:
        from pywebpush import WebPushException, webpush

        push = self._push or webpush
        c = channel.config
        subscription = {
            "endpoint": c["endpoint"],
            "keys": {"p256dh": c["p256dh"], "auth": c["auth"]},
        }
        pem = await self._keys.private_pem()
        try:
            await asyncio.to_thread(
                push,
                subscription_info=subscription,
                data=payload_of(alert),
                vapid_private_key=pem,
                vapid_claims={"sub": self._subject},
                timeout=TIMEOUT_S,
                ttl=24 * 3600,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                raise ProviderResponseError(
                    "web-push", "subscription expired: subscribe again"
                ) from exc
            raise ProviderUnavailableError(
                "web-push", f"HTTP {status}" if status else "push failed"
            ) from exc
