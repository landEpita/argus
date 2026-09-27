"""Public Telegram channels, read from their web preview (t.me/s/<channel>)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Protocol

from pydantic import Field, StringConstraints

from argus.domain.base import DomainModel

# Telegram usernames: 5-32 characters, letters, digits and underscores, starting with a letter.
ChannelHandle = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{4,31}$")]


class TelegramPost(DomainModel):
    id: str = Field(description="'channel/123'")
    channel: str
    channel_title: str | None = None
    text: str | None = None
    published_at: datetime
    url: str
    views: str | None = Field(default=None, description="As Telegram shows it: '12.3K'")
    has_media: bool = False
    countries: tuple[str, ...] = ()


class ChannelReader(Protocol):
    async def read(self, channel: str) -> list[TelegramPost]: ...
