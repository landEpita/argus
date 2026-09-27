"""
Analysis: the Country Signal Index and converging signals, composed from the
other services' outputs (no upstream of its own).

Its inputs are plain async functions, wired to the real services in the
composition root: the analysis depends on what it needs, not on who serves it.

Inputs fail independently. Every response lists its inputs with their status,
so a score computed without, say, the news feed says so instead of just
looking low.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.domain.convergence import Convergence, SignalKind, SignalPoint, find
from argus.domain.countries import CountryIndex, country_index
from argus.domain.events import EventFeed, GeoEvent
from argus.domain.news import Story
from argus.domain.signal_index import (
    Baselines,
    CountrySignal,
    HistoryPoint,
    SignalHistoryRepository,
    baselines_from,
    compute,
)
from argus.infra.cache import Cache
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError, NoProviderError

logger = logging.getLogger(__name__)

RESULT_TTL_S = 300.0
EVENT_LIMIT = 10_000
HISTORY_DAYS = 7
RETENTION_DAYS = 30
BASELINE_DAYS = 7
BASELINE_TTL_S = 3600.0
MAX_CONVERGENCES = 100
# Only "this input is missing" is tolerated; anything else is a bug and surfaces.
_MISSING = (AllProvidersFailedError, NoProviderError)
_SIGNALS: PydanticCodec[list[CountrySignal]] = PydanticCodec(list[CountrySignal])
_CONVERGENCE: PydanticCodec[list[Convergence]] = PydanticCodec(list[Convergence])


@dataclass(frozen=True, slots=True)
class InputStatus:
    name: str
    ok: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Analysed[T]:
    items: T
    inputs: list[InputStatus]


@dataclass(frozen=True, slots=True)
class CountryDetail:
    iso2: str
    name: str
    signal: CountrySignal | None
    history: list[HistoryPoint]
    stories: list[Story]
    inputs: list[InputStatus]


async def _safely[T](
    name: str, load: Callable[[], Awaitable[list[T]]]
) -> tuple[list[T], InputStatus]:
    try:
        return await load(), InputStatus(name, ok=True)
    except _MISSING as exc:
        return [], InputStatus(name, ok=False, error=str(exc))


class AnalysisService:
    def __init__(
        self,
        *,
        events: Callable[[EventFeed, timedelta], Awaitable[list[GeoEvent]]],
        stories: Callable[[timedelta, str | None], Awaitable[list[Story]]],
        military_aircraft: Callable[[], Awaitable[list[SignalPoint]]],
        military_vessels: Callable[[], Awaitable[list[SignalPoint]]],
        history: SignalHistoryRepository,
        cache: Cache,
        clock: WallClock | None = None,
        countries: CountryIndex | None = None,
    ) -> None:
        self._events = events
        self._stories = stories
        self._military_aircraft = military_aircraft
        self._military_vessels = military_vessels
        self._history = history
        self._cache = cache
        self._clock = clock or SystemWallClock()
        self._countries = countries or country_index()
        # What the cached results were computed from (the cache holds only the results).
        self._inputs: dict[str, list[InputStatus]] = {}
        self._baselines: Baselines = {}
        self._baselines_at: datetime | None = None

    # ── Country Signal Index ─────────────────────────────────────────────────

    async def country_signals(self) -> Analysed[list[CountrySignal]]:
        async def fresh() -> list[CountrySignal]:
            (
                (violence, s1),
                (alerts, s2),
                (outages, s3),
                (disasters, s4),
                (quakes, s5),
                (
                    stories,
                    s6,
                ),
            ) = await asyncio.gather(
                _safely(
                    "events:conflict", lambda: self._events(EventFeed.CONFLICT, timedelta(hours=24))
                ),
                _safely(
                    "events:air-alerts",
                    lambda: self._events(EventFeed.AIR_ALERTS, timedelta(hours=1)),
                ),
                _safely(
                    "events:internet-outages",
                    lambda: self._events(EventFeed.INTERNET_OUTAGES, timedelta(hours=48)),
                ),
                _safely(
                    "events:disaster-alerts",
                    lambda: self._events(EventFeed.DISASTER_ALERTS, timedelta(days=7)),
                ),
                _safely(
                    "events:earthquakes",
                    lambda: self._events(EventFeed.EARTHQUAKES, timedelta(hours=24)),
                ),
                _safely("news", lambda: self._stories(timedelta(hours=24), None)),
            )
            self._inputs["signals"] = [s1, s2, s3, s4, s5, s6]
            baselines = await self._current_baselines()
            return compute(
                violence=violence,
                air_alerts=alerts,
                outages=outages,
                disasters=disasters,
                earthquakes=quakes,
                stories=stories,
                names={c.iso2: c.name for c in self._countries.all()},
                at=self._clock.utcnow(),
                baselines=baselines,
            )

        signals = await self._cache.get_or_set("analysis:signals", RESULT_TTL_S, fresh, _SIGNALS)
        # Zero-score countries are stored for the baselines, but not listed.
        listed = [s for s in signals if s.score > 0]
        return Analysed(items=listed, inputs=self._inputs.get("signals", []))

    async def _current_baselines(self) -> Baselines:
        """A week of snapshots, re-read at most hourly (they only change hourly)."""
        now = self._clock.utcnow()
        stale = (
            self._baselines_at is None
            or (now - self._baselines_at).total_seconds() > BASELINE_TTL_S
        )
        if stale:
            samples = await self._history.samples(now - timedelta(days=BASELINE_DAYS))
            self._baselines = baselines_from(samples)
            self._baselines_at = now
        return self._baselines

    async def country(self, iso2: str) -> CountryDetail | None:
        country = self._countries.get(iso2)
        if country is None:
            return None
        result = await self.country_signals()
        history = await self._history.history(
            country.iso2, self._clock.utcnow() - timedelta(days=HISTORY_DAYS)
        )
        stories, _ = await _safely("news", lambda: self._stories(timedelta(hours=24), country.iso2))
        return CountryDetail(
            iso2=country.iso2,
            name=country.name,
            signal=next((s for s in result.items if s.iso2 == country.iso2), None),
            history=history,
            stories=stories[:10],
            inputs=result.inputs,
        )

    async def snapshot(self) -> int:
        """Store the current scores and raw values (called hourly by the snapshotter)."""
        await self.country_signals()
        signals = await self._cache.get("analysis:signals", _SIGNALS) or []
        now = self._clock.utcnow()
        await self._history.save(signals, now)
        await self._history.prune(now - timedelta(days=RETENTION_DAYS))
        self._baselines_at = None  # new samples: recompute on next use
        return len(signals)

    # ── Converging signals ───────────────────────────────────────────────────

    async def convergence(self) -> Analysed[list[Convergence]]:
        async def fresh() -> list[Convergence]:
            loaders: dict[str, Callable[[], Awaitable[list[SignalPoint]]]] = {
                "events:conflict": lambda: self._points(
                    EventFeed.CONFLICT, timedelta(hours=6), SignalKind.REPORTED_VIOLENCE
                ),
                "events:air-alerts": lambda: self._points(
                    EventFeed.AIR_ALERTS, timedelta(hours=1), SignalKind.AIR_ALERT
                ),
                "events:disaster-alerts": lambda: self._points(
                    EventFeed.DISASTER_ALERTS,
                    timedelta(days=7),
                    SignalKind.DISASTER,
                    keep=lambda e: (e.severity or 0) >= 2 / 3,  # orange and red alerts
                ),
                "events:earthquakes": lambda: self._points(
                    EventFeed.EARTHQUAKES,
                    timedelta(hours=24),
                    SignalKind.DISASTER,
                    keep=lambda e: (e.magnitude or 0) >= 5,
                ),
                "events:fires": lambda: self._points(
                    EventFeed.FIRES,
                    timedelta(hours=24),
                    SignalKind.FIRE,
                    keep=lambda e: (e.severity or 0) >= 0.5,  # strong hotspots only
                ),
                "aviation:military": self._military_aircraft,
                "maritime:military": self._military_vessels,
            }
            results = await asyncio.gather(*(_safely(n, f) for n, f in loaders.items()))
            self._inputs["convergence"] = [status for _, status in results]
            return find(p for found, _ in results for p in found)[:MAX_CONVERGENCES]

        items = await self._cache.get_or_set(
            "analysis:convergence", RESULT_TTL_S, fresh, _CONVERGENCE
        )
        return Analysed(items=items, inputs=self._inputs.get("convergence", []))

    async def _points(
        self,
        feed: EventFeed,
        window: timedelta,
        kind: SignalKind,
        keep: Callable[[GeoEvent], bool] = lambda _: True,
    ) -> list[SignalPoint]:
        points: list[SignalPoint] = []
        for e in await self._events(feed, window):
            if not keep(e):
                continue
            country = e.details.get("country_iso2")
            points.append(
                SignalPoint(
                    kind=kind,
                    id=e.id,
                    label=e.title,
                    position=e.position,
                    at=e.occurred_at,
                    country=country if isinstance(country, str) else None,
                )
            )
        return points
