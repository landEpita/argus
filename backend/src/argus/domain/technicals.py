"""
Technical reading of daily bars: moving averages, RSI, 52-week range, and
support/resistance levels.

Everything here is descriptive arithmetic on past prices, not a forecast.
The ``METHOD`` strings are returned with every reading so the interface can
say exactly how each number was obtained.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from itertools import pairwise

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.markets import Candle

SESSIONS_PER_YEAR = 252
RSI_PERIOD = 14
PIVOT_WINDOW = 5  # a pivot high is the highest high of the 5 sessions each side
LEVEL_TOLERANCE = 0.015  # pivots within 1.5 % of each other form one level
MIN_TOUCHES = 2
LEVELS_PER_SIDE = 3

METHOD = (
    "Simple moving averages of daily closes.",
    f"RSI: Wilder's {RSI_PERIOD}-session relative strength index.",
    f"52-week range: highest high and lowest low of the last {SESSIONS_PER_YEAR} sessions.",
    f"Levels: pivot highs and lows ({PIVOT_WINDOW} sessions each side), merged when within "
    f"{LEVEL_TOLERANCE * 100:g} % of each other, kept when touched at least {MIN_TOUCHES} "
    "times; the nearest above and below the last close are shown.",
)


class LevelKind(StrEnum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class Level(DomainModel):
    kind: LevelKind
    price: float
    touches: int
    last_touch: date
    distance_pct: float = Field(description="From the last close; negative = below")


class Technicals(DomainModel):
    as_of: date
    close: float
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    high_52w: float
    low_52w: float
    sessions: int = Field(description="Bars the reading is based on")
    levels: tuple[Level, ...]
    method: tuple[str, ...] = METHOD


def sma(closes: Sequence[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> float | None:
    if len(closes) <= period:
        return None
    deltas = [b - a for a, b in pairwise(closes)]
    gain = sum(max(d, 0.0) for d in deltas[:period]) / period
    loss = sum(max(-d, 0.0) for d in deltas[:period]) / period
    for d in deltas[period:]:
        gain = (gain * (period - 1) + max(d, 0.0)) / period
        loss = (loss * (period - 1) + max(-d, 0.0)) / period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def _pivots(candles: Sequence[Candle], window: int) -> list[tuple[float, date]]:
    points: list[tuple[float, date]] = []
    for i in range(window, len(candles) - window):
        around = candles[i - window : i + window + 1]
        c = candles[i]
        if c.high == max(x.high for x in around):
            points.append((c.high, c.day))
        if c.low == min(x.low for x in around):
            points.append((c.low, c.day))
    return points


def levels(candles: Sequence[Candle], close: float) -> tuple[Level, ...]:
    clusters: list[list[tuple[float, date]]] = []
    for price, day in sorted(_pivots(candles, PIVOT_WINDOW)):
        last = clusters[-1] if clusters else None
        if last is not None:
            mean = sum(p for p, _ in last) / len(last)
            if (price - mean) / mean <= LEVEL_TOLERANCE:
                last.append((price, day))
                continue
        clusters.append([(price, day)])

    found = [
        Level(
            kind=LevelKind.SUPPORT if mean < close else LevelKind.RESISTANCE,
            price=round(mean, 6),
            touches=len(group),
            last_touch=max(d for _, d in group),
            distance_pct=round((mean - close) / close * 100, 2),
        )
        for group in clusters
        if len(group) >= MIN_TOUCHES
        for mean in [sum(p for p, _ in group) / len(group)]
    ]
    nearest = sorted(found, key=lambda lv: abs(lv.distance_pct))
    supports = [lv for lv in nearest if lv.kind is LevelKind.SUPPORT][:LEVELS_PER_SIDE]
    resistances = [lv for lv in nearest if lv.kind is LevelKind.RESISTANCE][:LEVELS_PER_SIDE]
    return tuple(sorted(supports + resistances, key=lambda lv: lv.price, reverse=True))


def analyse(candles: Sequence[Candle]) -> Technicals | None:
    """None when there are no bars at all; indicators needing more history are None."""
    if not candles:
        return None
    closes = [c.close for c in candles]
    year = candles[-SESSIONS_PER_YEAR:]
    last = candles[-1]

    def rounded(v: float | None) -> float | None:
        return None if v is None else round(v, 6)

    return Technicals(
        as_of=last.day,
        close=last.close,
        sma_20=rounded(sma(closes, 20)),
        sma_50=rounded(sma(closes, 50)),
        sma_200=rounded(sma(closes, 200)),
        rsi_14=None if (r := rsi(closes)) is None else round(r, 1),
        high_52w=max(c.high for c in year),
        low_52w=min(c.low for c in year),
        sessions=len(candles),
        levels=levels(year, last.close),
    )
