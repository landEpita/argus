"""Macro context: sentiment gauges, the US Treasury yield curve, the economic calendar."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability


class SentimentReading(DomainModel):
    value: int = Field(ge=0, le=100)
    label: str
    at: datetime


class SentimentIndex(DomainModel):
    id: str
    name: str
    latest: SentimentReading
    history: tuple[SentimentReading, ...] = Field(description="Most recent first")
    source: str


class YieldPoint(DomainModel):
    tenor: str = Field(description="'3 Mo', '10 Yr'")
    years: float
    rate_pct: float


class YieldCurve(DomainModel):
    date: date
    points: tuple[YieldPoint, ...]
    previous: tuple[YieldPoint, ...] = Field(default=(), description="Previous business day")
    inverted_2y_10y: bool | None = None
    source: str


class Impact(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    HOLIDAY = "holiday"


class CalendarEvent(DomainModel):
    title: str
    currency: str = Field(description="Currency the release concerns (FX-desk convention)")
    at: datetime
    impact: Impact
    forecast: str | None = None
    previous: str | None = None


class EmptyQuery(DomainModel):
    pass


SENTIMENT: Capability[EmptyQuery, list[SentimentIndex]] = Capability(
    "macro.sentiment", "Market sentiment gauges (fear & greed)."
)
YIELD_CURVE: Capability[EmptyQuery, YieldCurve] = Capability(
    "macro.yield_curve", "US Treasury par yield curve, latest business day."
)
ECONOMIC_CALENDAR: Capability[EmptyQuery, list[CalendarEvent]] = Capability(
    "macro.calendar", "This week's scheduled economic releases."
)
