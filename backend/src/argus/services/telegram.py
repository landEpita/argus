"""Telegram channels chosen by the user, merged newest first."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from argus.domain.telegram import ChannelHandle, ChannelReader, TelegramPost
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.codec import PydanticCodec
from argus.infra.health import HealthRegistry
from argus.providers.errors import NoProviderError, ProviderError

logger = logging.getLogger(__name__)

_CODEC: PydanticCodec[list[TelegramPost]] = PydanticCodec(list[TelegramPost])
_HANDLE: TypeAdapter[str] = TypeAdapter(ChannelHandle)
MAX_CHANNELS = 20
CHANNEL_TTL_S = 60.0
CHANNEL_STALE_TTL_S = 3600.0
PROVIDER = "telegram"


class InvalidChannelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChannelStatus:
    channel: str
    posts: int
    error: str | None


@dataclass(frozen=True, slots=True)
class TelegramPage:
    items: list[TelegramPost]
    channels: list[ChannelStatus]


def normalise_channels(raw: Sequence[str]) -> list[str]:
    """Validate handles; accept '@name' and 't.me/name' as users paste them."""
    seen: dict[str, None] = {}
    for item in raw:
        handle = item.strip().removeprefix("https://").removeprefix("t.me/").removeprefix("@")
        handle = handle.removeprefix("s/").strip("/")
        if not handle:
            continue
        try:
            seen.setdefault(_HANDLE.validate_python(handle).lower(), None)
        except ValidationError as exc:
            raise InvalidChannelError(f"not a Telegram channel name: {item!r}") from exc
    if len(seen) > MAX_CHANNELS:
        raise InvalidChannelError(f"at most {MAX_CHANNELS} channels")
    return list(seen)


CAPABILITY = "intel.telegram"


class TelegramService:
    """``reader=None`` means Telegram is switched off on this server."""

    def __init__(self, reader: ChannelReader | None, cache: Cache, health: HealthRegistry) -> None:
        self._reader = reader
        self._cache = cache
        self._health = health
        self._semaphore = asyncio.Semaphore(4)
        if reader is not None:
            health.register(PROVIDER)

    async def posts(self, channels: Sequence[str], limit: int) -> TelegramPage:
        if self._reader is None:
            raise NoProviderError(CAPABILITY)
        reader = self._reader
        handles = normalise_channels(channels)
        results = await asyncio.gather(*(self._channel(reader, h) for h in handles))
        posts = sorted(
            (p for status, found in results for p in found),
            key=lambda p: p.published_at,
            reverse=True,
        )
        return TelegramPage(items=posts[:limit], channels=[status for status, _ in results])

    async def _channel(
        self, reader: ChannelReader, handle: str
    ) -> tuple[ChannelStatus, list[TelegramPost]]:
        async def fetch() -> list[TelegramPost]:
            async with self._semaphore:
                found = await reader.read(handle)
            self._health.record_success(PROVIDER)
            return found

        try:
            posts = await get_or_set_with_fallback(
                self._cache,
                f"telegram:{handle}",
                CHANNEL_TTL_S,
                CHANNEL_STALE_TTL_S,
                fetch,
                _CODEC,
                recoverable=(ProviderError,),
            )
        except ProviderError as exc:
            logger.warning("telegram channel failed", extra={"channel": handle, "error": str(exc)})
            self._health.record_failure(PROVIDER, str(exc))
            return ChannelStatus(handle, 0, str(exc)), []
        return ChannelStatus(handle, len(posts), None), posts
