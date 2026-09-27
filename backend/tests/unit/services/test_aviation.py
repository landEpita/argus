from argus.domain.aviation import AIRCRAFT_STATES, MILITARY_AIRCRAFT, AircraftQuery
from argus.domain.geo import BoundingBox
from argus.infra.cache import InMemoryTTLCache
from argus.providers.registry import ProviderRegistry
from argus.services.aviation import AviationService
from tests.fakes import FakeClock, StubAircraftFetcher, make_aircraft

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
    await service.aircraft(AircraftQuery())
    clock.advance(16)
    await service.aircraft(AircraftQuery())
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
