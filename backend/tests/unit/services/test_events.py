from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from argus.domain.events import (
    EARTHQUAKES,
    FIRES,
    EventCategory,
    EventFeed,
    EventQuery,
    GeoEvent,
)
from argus.domain.geo import BoundingBox, GeoPoint
from argus.infra.cache import InMemoryTTLCache
from argus.providers.base import Fetcher
from argus.providers.registry import ProviderRegistry
from argus.services.events import EventsService
from tests.fakes import FakeClock, FakeWallClock

NOW = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


def event(
    i: str, *, hours_ago: float, severity: float | None, lat: float = 10, lon: float = 10
) -> GeoEvent:
    return GeoEvent(
        id=f"t:{i}",
        category=EventCategory.EARTHQUAKE,
        title=i,
        position=GeoPoint(lat=lat, lon=lon),
        occurred_at=NOW - timedelta(hours=hours_ago),
        severity=severity,
        source="t",
    )


class StubFeed(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "stub"

    def __init__(self, events: list[GeoEvent]) -> None:
        self.events = events
        self.queries: list[EventQuery] = []

    async def extract(self, params: Any) -> Any:
        return None

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        self.queries.append(query)
        return self.events


def service(
    feed: StubFeed, capability: Any = EARTHQUAKES, clock: FakeWallClock | None = None
) -> EventsService:
    registry = ProviderRegistry()
    registry.register(capability, feed)
    return EventsService(
        registry, InMemoryTTLCache(clock=FakeClock()), clock=clock or FakeWallClock(NOW)
    )


SAMPLE = [
    event("old", hours_ago=30, severity=0.9),
    event("mild", hours_ago=1, severity=0.2),
    event("strong", hours_ago=2, severity=0.8),
    event("unscored", hours_ago=0.5, severity=None),
    event("far", hours_ago=1, severity=0.5, lat=-40, lon=150),
]


async def test_window_filter_and_severity_order() -> None:
    page = await service(StubFeed(SAMPLE)).events(
        EventFeed.EARTHQUAKES, window=timedelta(hours=24), bbox=None, limit=100
    )
    assert [e.id for e in page.items] == ["t:strong", "t:far", "t:mild", "t:unscored"]
    assert page.window_start == NOW - timedelta(hours=24)
    assert page.truncated is False


async def test_bbox_filter_is_exact() -> None:
    box = BoundingBox(west=0, south=0, east=20, north=20)
    page = await service(StubFeed(SAMPLE)).events(
        EventFeed.EARTHQUAKES, window=timedelta(hours=24), bbox=box, limit=100
    )
    assert "t:far" not in [e.id for e in page.items]


async def test_limit_truncates_keeping_the_most_severe() -> None:
    page = await service(StubFeed(SAMPLE)).events(
        EventFeed.EARTHQUAKES, window=timedelta(hours=24), bbox=None, limit=1
    )
    assert [e.id for e in page.items] == ["t:strong"]
    assert page.truncated is True


async def test_window_is_capped_by_the_feed_policy() -> None:
    page = await service(StubFeed(SAMPLE), FIRES).events(
        EventFeed.FIRES, window=timedelta(days=60), bbox=None, limit=10
    )
    assert page.window_start == NOW - timedelta(days=5)


async def test_requests_within_a_ttl_share_one_upstream_call() -> None:
    clock = FakeWallClock(NOW)
    feed = StubFeed(SAMPLE)
    svc = service(feed, clock=clock)
    await svc.events(EventFeed.EARTHQUAKES, window=timedelta(hours=24), bbox=None, limit=10)
    clock.now = NOW + timedelta(seconds=20)
    await svc.events(EventFeed.EARTHQUAKES, window=timedelta(hours=24), bbox=None, limit=10)
    assert len(feed.queries) == 1
    assert feed.queries[0].since <= NOW - timedelta(hours=24)


@pytest.mark.parametrize(
    ("capability", "feed", "expect_bbox"),
    [(EARTHQUAKES, EventFeed.EARTHQUAKES, False), (FIRES, EventFeed.FIRES, True)],
)
async def test_only_bbox_aware_feeds_get_the_box_upstream(
    capability: Any, feed: EventFeed, expect_bbox: bool
) -> None:
    stub = StubFeed([])
    box = BoundingBox(west=1.23, south=2.34, east=3.45, north=4.56)
    await service(stub, capability).events(feed, window=timedelta(hours=1), bbox=box, limit=10)
    upstream = stub.queries[0].bbox
    assert (upstream is not None) is expect_bbox
    if upstream is not None:
        assert upstream == box.expanded_to_grid()


def test_available_feeds_lists_every_feed() -> None:
    feeds = service(StubFeed([])).available_feeds()
    assert set(feeds) == set(EventFeed)
    assert feeds[EventFeed.EARTHQUAKES] == ["stub"]
    assert feeds[EventFeed.CONFLICT] == []
