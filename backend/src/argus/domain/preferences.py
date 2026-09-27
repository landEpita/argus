"""Per-owner UI preferences: which layers are on and where the map was left."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints

from argus.domain.base import DomainModel
from argus.domain.geo import GeoPoint
from argus.domain.telegram import ChannelHandle

LayerId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class Viewport(DomainModel):
    center: GeoPoint
    zoom: float = Field(ge=0, le=22)


class Preferences(DomainModel):
    """
    Versioned so a future shape change can migrate stored documents instead of
    failing to validate them.
    """

    schema_version: Literal[1] = 1
    # None = "never chosen": the client applies its own defaults.
    enabled_layers: tuple[LayerId, ...] | None = Field(default=None, max_length=100)
    viewport: Viewport | None = None
    # Added after v1 shipped; optional, so stored v1 documents stay valid.
    projection: Literal["mercator", "globe"] | None = None
    telegram_channels: tuple[ChannelHandle, ...] | None = Field(default=None, max_length=20)


class StoredPreferences(DomainModel):
    preferences: Preferences
    updated_at: datetime | None


class PreferencesRepository(Protocol):
    async def get(self, owner: str) -> StoredPreferences | None: ...

    async def save(self, owner: str, preferences: Preferences) -> StoredPreferences: ...
