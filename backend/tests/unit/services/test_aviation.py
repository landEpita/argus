from datetime import UTC, datetime, timedelta

import pytest

from argus.domain.aviation import AIRCRAFT_STATES, MILITARY_AIRCRAFT, Aircraft, AircraftQuery
from argus.domain.geo import BoundingBox
from argus.infra.cache import InMemoryTTLCache
from argus.providers.errors import AllProvidersFailedError, ProviderUnavailableError
from argus.providers.registry import ProviderRegistry
from argus.services.aviation import AviationService, Coverage
from tests.fakes import FakeClock, FakeWallClock, StubAircraftFetcher, make_aircraft

PARIS = BoundingBox(west=2.2, south=48.8, east=2.5, north=48.9)

SKY = [
    make_aircraft("aaaaa1", lat=48.85, lon=2.35),  # inside Paris box
    make_aircraft("aaaaa2", lat=48.85, lon=2.35, on_ground=True),  # inside, grounded
    make_aircraft("aaaaa3", lat=48.95, lon=2.35),  # inside grid-expanded box only
]


def build(clock: FakeClock | None = None) -> tuple[AviationService, StubAircraftFetcher]:
    stub = StubAircraftFetcher(lambda _: SKY)
    registry = ProviderRegistry()
    registry.register(AIRCRAFT_STATES, stub)
    cache = InMemoryTTLCache(clock=clock or FakeClock())
    return AviationService(registry, cache, ttl_s=15), stub


async def test_filters_to_exact_box_and_hides_grounded_by_default() -> None:
    service, _ = build()
    result = await service.aircraft(AircraftQuery(bbox=PARIS))
    assert [a.icao24 for a in result] == ["aaaaa1"]


async def test_can_include_grounded_aircraft() -> None:
    service, _ = build()
    result = await service.aircraft(AircraftQuery(bbox=PARIS, include_on_ground=True))
    assert [a.icao24 for a in result] == ["aaaaa1", "aaaaa2"]


async def test_asks_upstream_for_grid_box_including_grounded() -> None:
    service, stub = build()
    await service.aircraft(AircraftQuery(bbox=PARIS))
    [upstream] = stub.queries
    assert upstream.include_on_ground is True
    assert upstream.bbox == PARIS.expanded_to_grid()


async def test_nearby_viewports_hit_the_cache() -> None:
    service, stub = build()
    await service.aircraft(AircraftQuery(bbox=PARIS))
    await service.aircraft(
        AircraftQuery(bbox=BoundingBox(west=2.21, south=48.81, east=2.49, north=48.89))
    )
    await service.aircraft(AircraftQuery(bbox=PARIS, include_on_ground=True))
    assert len(stub.queries) == 1


async def test_cache_expires() -> None:
    clock = FakeClock()
    service, stub = build(clock)
    await service.aircraft(AircraftQuery(bbox=PARIS))
    clock.advance(16)
    await service.aircraft(AircraftQuery(bbox=PARIS))
    assert len(stub.queries) == 2


async def test_world_query_returns_all_airborne() -> None:
    service, stub = build()
    result = await service.aircraft(AircraftQuery())
    assert [a.icao24 for a in result] == ["aaaaa1", "aaaaa3"]
    assert stub.queries[0].bbox is None


async def test_military_is_one_world_entry_filtered_per_box() -> None:
    stub = StubAircraftFetcher(lambda _: SKY)
    registry = ProviderRegistry()
    registry.register(MILITARY_AIRCRAFT, stub)
    service = AviationService(
        registry, InMemoryTTLCache(clock=FakeClock()), ttl_s=15, military_ttl_s=30
    )
    inside = await service.military(AircraftQuery(bbox=PARIS))
    everywhere = await service.military(AircraftQuery())
    assert [a.icao24 for a in inside] == ["aaaaa1"]
    assert [a.icao24 for a in everywhere] == ["aaaaa1", "aaaaa3"]
    assert len(stub.queries) == 1
    assert stub.queries[0].bbox is None


EUROPE = BoundingBox(west=-10, south=35, east=30, north=60)  # far wider than 250 NM


def flaky(
    clock: FakeClock, wall: FakeWallClock
) -> tuple[AviationService, dict[str, bool], StubAircraftFetcher]:
    """World queries fail when `state["down"]`; box queries always answer."""
    state = {"down": False}

    def answer(q: AircraftQuery) -> list[Aircraft]:
        if q.bbox is None and state["down"]:
            raise ProviderUnavailableError("opensky", "HTTP 429")
        return SKY

    stub = StubAircraftFetcher(answer, name="opensky")
    registry = ProviderRegistry()
    registry.register(AIRCRAFT_STATES, stub)
    service = AviationService(
        registry, InMemoryTTLCache(clock=clock), ttl_s=15, world_ttl_s=300, clock=wall
    )
    return service, state, stub


async def test_wide_views_share_one_world_snapshot() -> None:
    service, stub = build()
    view = await service.aircraft_view(AircraftQuery(bbox=EUROPE))
    await service.aircraft_view(
        AircraftQuery(bbox=BoundingBox(west=0, south=40, east=20, north=55))
    )
    assert view.coverage is Coverage.WORLD
    assert view.stale_age_s is None
    assert [q.bbox for q in stub.queries] == [None]  # one world request for both views


async def test_a_refused_world_snapshot_falls_back_to_the_last_good_one() -> None:
    clock, wall = FakeClock(), FakeWallClock(datetime(2026, 9, 27, 18, tzinfo=UTC))
    service, state, _ = flaky(clock, wall)
    await service.aircraft_view(AircraftQuery(bbox=EUROPE))
    state["down"] = True
    clock.advance(400)
    wall.now = wall.now + timedelta(seconds=400)
    view = await service.aircraft_view(AircraftQuery(bbox=EUROPE))
    assert view.coverage is Coverage.WORLD
    assert view.stale_age_s == 400  # labelled, not passed off as live
    assert len(view.items) == 2


async def test_without_any_snapshot_the_centre_of_the_view_is_served() -> None:
    clock, wall = FakeClock(), FakeWallClock(datetime(2026, 9, 27, 18, tzinfo=UTC))
    service, state, stub = flaky(clock, wall)
    state["down"] = True
    view = await service.aircraft_view(AircraftQuery(bbox=EUROPE))
    assert view.coverage is Coverage.REGIONAL
    assert view.circle is not None
    lat, lon, radius = view.circle
    assert (round(lat, 1), round(lon, 1), radius) == (47.5, 10.0, 250)
    from argus.domain.geo import covering_circle

    [regional] = [q.bbox for q in stub.queries if q.bbox is not None]
    assert regional is not None
    assert covering_circle(regional)[2] <= 250  # adsb.lol accepts it
    with pytest.raises(AllProvidersFailedError):
        await service.aircraft_view(AircraftQuery())  # no view, no centre: nothing to fall back on
