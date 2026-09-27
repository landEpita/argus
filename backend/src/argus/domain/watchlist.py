"""
Watchlists: named sets of things to keep an eye on (aircraft, vessels,
tickers, countries, keywords). Later phases use them to highlight map objects
and to trigger alerts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field, ValidationInfo, field_validator

from argus.domain.base import DomainModel

MAX_ITEMS_PER_WATCHLIST = 500
MAX_WATCHLISTS_PER_OWNER = 50


class WatchKind(StrEnum):
    AIRCRAFT = "aircraft"
    VESSEL = "vessel"
    TICKER = "ticker"
    COUNTRY = "country"
    KEYWORD = "keyword"


def _matching(pattern: str, transform: Callable[[str], str], what: str) -> Callable[[str], str]:
    compiled = re.compile(pattern)

    def normalise(raw: str) -> str:
        value = transform(raw.strip())
        if not compiled.fullmatch(value):
            raise ValueError(f"invalid {what}: {raw!r}")
        return value

    return normalise


# One normalisation strategy per kind, so "3C6444" and "3c6444 " are the same aircraft.
_NORMALISERS: dict[WatchKind, Callable[[str], str]] = {
    WatchKind.AIRCRAFT: _matching(r"[0-9a-f]{6}", str.lower, "ICAO 24-bit address"),
    WatchKind.VESSEL: _matching(r"\d{9}", str.strip, "MMSI (9 digits)"),
    WatchKind.TICKER: _matching(r"\^?[A-Z0-9][A-Z0-9.\-=]{0,19}", str.upper, "ticker"),
    WatchKind.COUNTRY: _matching(r"[A-Z]{2}", str.upper, "ISO 3166-1 alpha-2 code"),
    WatchKind.KEYWORD: _matching(r"\S(?:.{0,98}\S)?", lambda s: " ".join(s.split()), "keyword"),
}


class WatchItem(DomainModel):
    kind: WatchKind
    value: str = Field(max_length=200)
    label: str | None = Field(default=None, max_length=100)

    @field_validator("value")
    @classmethod
    def _normalise_value(cls, value: str, info: ValidationInfo) -> str:
        kind = info.data.get("kind")
        if kind is None:  # kind itself was invalid; that error is already reported
            return value
        return _NORMALISERS[kind](value)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, label: str | None) -> str | None:
        return (label.strip() or None) if label else None


class WatchlistDraft(DomainModel):
    """What a client submits to create or replace a watchlist."""

    name: str = Field(min_length=1, max_length=100)
    items: tuple[WatchItem, ...] = Field(default=(), max_length=MAX_ITEMS_PER_WATCHLIST)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @field_validator("items")
    @classmethod
    def _no_duplicates(cls, items: tuple[WatchItem, ...]) -> tuple[WatchItem, ...]:
        seen: set[tuple[WatchKind, str]] = set()
        for item in items:
            key = (item.kind, item.value)
            if key in seen:
                raise ValueError(f"duplicate item: {item.kind}:{item.value}")
            seen.add(key)
        return items


class Watchlist(DomainModel):
    id: UUID
    name: str
    items: tuple[WatchItem, ...]
    created_at: datetime
    updated_at: datetime


class WatchlistRepository(Protocol):
    """Persistence port. Raises ConflictError on a duplicate name per owner."""

    async def list(self, owner: str) -> list[Watchlist]: ...

    async def count(self, owner: str) -> int: ...

    async def get(self, owner: str, watchlist_id: UUID) -> Watchlist | None: ...

    async def create(self, owner: str, draft: WatchlistDraft) -> Watchlist: ...

    async def replace(
        self, owner: str, watchlist_id: UUID, draft: WatchlistDraft
    ) -> Watchlist | None: ...

    async def delete(self, owner: str, watchlist_id: UUID) -> bool: ...
