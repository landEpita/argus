import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from argus.domain.convergence import SignalKind, SignalPoint
from argus.domain.events import EventCategory, EventFeed, GeoEvent
from argus.domain.geo import GeoPoint
from argus.domain.news import Story
from argus.domain.signal_index import Component, CountrySignal, HistoryPoint, ScoreMode
from argus.infra.cache import InMemoryTTLCache
from argus.providers.errors import (
    AllProvidersFailedError,
    NoProviderError,
    ProviderUnavailableError,
)
from argus.services.analysis import AnalysisService
from argus.services.snapshotter import SignalSnapshotter
from tests.fakes import FakeClock, FakeWallClock
from tests.unit.domain.test_signals import story

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


def event(
    i: str,
    country: str,
    category: EventCategory = EventCategory.ARMED_CONFLICT,
    lat: float = 48.5,
    lon: float = 35.0,
    details: dict[str, Any] | None = None,
    **kw: Any,
) -> GeoEvent:
    return GeoEvent(
        id=i,
        category=category,
        title=i,
        position=GeoPoint(lat=lat, lon=lon),
        occurred_at=NOW,
        source="t",
        details={"country_iso2": country, **(details or {})},
        **kw,
    )


class MemoryHistory:
    def __init__(self) -> None:
        self.saved: list[tuple[datetime, list[CountrySignal]]] = []
        self.pruned: list[datetime] = []

    async def save(self, signals: Any, at: datetime) -> None:
        self.saved.append((at, list(signals)))

    async def history(self, iso2: str, since: datetime) -> list[HistoryPoint]:
        return [
            HistoryPoint(at=at, score=s.score)
            for at, sigs in self.saved
            for s in sigs
            if s.iso2 == iso2 and at >= since
        ]

    async def samples(self, since: datetime) -> list[tuple[str, dict[Component, float]]]:
        return [
            (s.iso2, {c.component: c.raw for c in s.components})
            for at, sigs in self.saved
            for s in sigs
            if at >= since
        ]

    async def prune(self, before: datetime) -> int:
        self.pruned.append(before)
        return 0


class Inputs:
    def __init__(self) -> None:
        self.feeds: dict[EventFeed, list[GeoEvent] | Exception] = {}
        self.stories: list[Story] | Exception = []
        self.aircraft: list[SignalPoint] | Exception = []
        self.calls = 0

    async def events(self, feed: EventFeed, window: timedelta) -> list[GeoEvent]:
        self.calls += 1
        result = self.feeds.get(feed, [])
        if isinstance(result, Exception):
            raise result
        return result

    async def load_stories(self, window: timedelta, country: str | None) -> list[Story]:
        if isinstance(self.stories, Exception):
            raise self.stories
        return [s for s in self.stories if country is None or country in s.countries]

    async def military(self) -> list[SignalPoint]:
        if isinstance(self.aircraft, Exception):
            raise self.aircraft
        return self.aircraft

    async def vessels(self) -> list[SignalPoint]:
        raise NoProviderError("maritime.vessel_positions")


def service(inputs: Inputs, history: MemoryHistory | None = None) -> AnalysisService:
    return AnalysisService(
        events=inputs.events,
        stories=inputs.load_stories,
        military_aircraft=inputs.military,
        military_vessels=inputs.vessels,
        history=history or MemoryHistory(),
        cache=InMemoryTTLCache(clock=FakeClock()),
        clock=FakeWallClock(NOW),
    )


async def test_index_reports_missing_inputs_instead_of_failing() -> None:
    inputs = Inputs()
    inputs.feeds[EventFeed.CONFLICT] = [event("v1", "UA", severity=1.0)]
    inputs.feeds[EventFeed.AIR_ALERTS] = AllProvidersFailedError(
        "events.air-alerts", [ProviderUnavailableError("ubilling", "down")]
    )
    inputs.feeds[EventFeed.INTERNET_OUTAGES] = NoProviderError("events.internet-outages")
    result = await service(inputs).country_signals()
    assert [s.iso2 for s in result.items] == ["UA"]
    status = {i.name: i.ok for i in result.inputs}
    assert status["events:conflict"] is True
    assert status["events:air-alerts"] is False
    assert status["events:internet-outages"] is False
    assert status["news"] is True


async def test_results_and_their_inputs_are_cached_together() -> None:
    inputs = Inputs()
    svc = service(inputs)
    first = await svc.country_signals()
    calls = inputs.calls
    second = await svc.country_signals()
    assert inputs.calls == calls
    assert second.inputs == first.inputs


async def test_bugs_are_not_swallowed() -> None:
    inputs = Inputs()
    inputs.feeds[EventFeed.CONFLICT] = KeyError("bug")
    with pytest.raises(KeyError):
        await service(inputs).country_signals()


async def test_country_detail_with_history_and_stories() -> None:
    inputs = Inputs()
    inputs.feeds[EventFeed.CONFLICT] = [event("v1", "UA", severity=1.0)]
    inputs.stories = [story("s1", ("UA",), 2), story("s2", ("FR",), 1)]
    history = MemoryHistory()
    svc = service(inputs, history)
    await svc.snapshot()
    detail = await svc.country("ua")
    assert detail is not None
    assert detail.name == "Ukraine"
    assert detail.signal is not None
    assert [p.score for p in detail.history] == [detail.signal.score]
    assert [s.id for s in detail.stories] == ["s1"]
    assert history.pruned == [NOW - timedelta(days=30)]
    assert await svc.country("zz") is None


async def test_quiet_country_has_no_signal_but_still_a_page() -> None:
    detail = await service(Inputs()).country("FR")
    assert detail is not None
    assert detail.signal is None


async def test_convergence_combines_kinds_and_reports_inputs() -> None:
    inputs = Inputs()
    inputs.feeds[EventFeed.CONFLICT] = [event("v1", "UA")]
    inputs.feeds[EventFeed.AIR_ALERTS] = [
        event("a1", "UA", EventCategory.AIR_RAID_ALERT, lat=48.2, lon=35.3)
    ]
    inputs.feeds[EventFeed.DISASTER_ALERTS] = [
        event("g-green", "UA", EventCategory.FLOOD, severity=1 / 3)
    ]
    inputs.feeds[EventFeed.EARTHQUAKES] = [
        event("q-small", "UA", EventCategory.EARTHQUAKE, magnitude=3.0)
    ]
    inputs.aircraft = [
        SignalPoint(
            SignalKind.MILITARY_AIRCRAFT, "aircraft:x", "RCH1", GeoPoint(lat=48.9, lon=35.9), NOW
        )
    ]
    result = await service(inputs).convergence()
    [c] = result.items
    assert {k.kind for k in c.kinds} == {
        SignalKind.REPORTED_VIOLENCE,
        SignalKind.AIR_ALERT,
        SignalKind.MILITARY_AIRCRAFT,
    }
    assert c.country == "UA"
    status = {i.name: i.ok for i in result.inputs}
    assert status["maritime:military"] is False
    assert status["aviation:military"] is True


async def test_snapshotter_runs_and_survives_failures() -> None:
    calls: list[str] = []

    class Flaky:
        async def snapshot(self) -> int:
            calls.append("x")
            if len(calls) == 1:
                raise RuntimeError("db down")
            return 3

    snapshotter = SignalSnapshotter(Flaky(), interval_s=0.001, first_delay_s=0)  # type: ignore[arg-type]
    await snapshotter.start()
    await snapshotter.start()  # idempotent
    for _ in range(100):
        if len(calls) >= 3:
            break
        await asyncio.sleep(0.005)
    await snapshotter.stop()
    await snapshotter.stop()
    assert len(calls) >= 3


async def test_volume_biased_components_become_relative_with_a_week_of_history() -> None:
    inputs = Inputs()
    busy_day = [event(f"v{i}", "GB", severity=1.0, details={"num_sources": 3}) for i in range(20)]
    inputs.feeds[EventFeed.CONFLICT] = busy_day
    history = MemoryHistory()
    first = service(inputs, history)
    absolute = (await first.country_signals()).items[0]
    assert absolute.has_baseline is False

    for _ in range(30):  # the same volume every hour: that is normal for GB
        await first.snapshot()
    relative = (await service(inputs, history).country_signals()).items
    assert relative == []  # at its usual level: no points, not listed

    inputs.feeds[EventFeed.CONFLICT] = busy_day * 4  # four times the usual
    spike = (await service(inputs, history).country_signals()).items[0]
    violence = next(c for c in spike.components if c.component is Component.REPORTED_VIOLENCE)
    assert spike.has_baseline is True
    assert violence.mode is ScoreMode.RELATIVE
    assert violence.baseline_mean is not None
    assert violence.points > 0
