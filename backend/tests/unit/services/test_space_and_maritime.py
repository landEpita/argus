import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from argus.adapters.aisstream import AisStreamRelay, VesselStore, VesselStoreFetcher
from argus.adapters.aisstream.messages import PositionUpdate
from argus.adapters.celestrak import CelestrakElementsFetcher
from argus.domain.maritime import VESSEL_POSITIONS, VesselQuery
from argus.domain.space import ORBITAL_ELEMENTS, ElementsQuery, OrbitalElements, SatelliteGroup
from argus.infra.cache import InMemoryTTLCache
from argus.providers.base import Fetcher
from argus.providers.registry import ProviderRegistry
from argus.services.maritime import MaritimeService
from argus.services.space import SpaceService
from tests.fakes import FakeClock, FakeWallClock, StubHttp

RAW = json.loads((Path(__file__).parents[2] / "fixtures" / "celestrak_stations.json").read_text())
ELEMENTS = CelestrakElementsFetcher(StubHttp()).transform(
    ElementsQuery(group=SatelliteGroup.STATIONS), RAW
)
EPOCH = ELEMENTS[0].epoch


class StubElements(Fetcher[ElementsQuery, list[OrbitalElements]]):
    provider_name = "stub"

    def __init__(self, elements: list[OrbitalElements]) -> None:
        self.elements = elements
        self.calls = 0

    async def extract(self, params: Any) -> Any:
        return None

    def transform(self, query: ElementsQuery, raw: Any) -> list[OrbitalElements]:
        self.calls += 1
        return self.elements


def space(stub: StubElements, clock: FakeWallClock) -> SpaceService:
    registry = ProviderRegistry()
    registry.register(ORBITAL_ELEMENTS, stub)
    return SpaceService(registry, InMemoryTTLCache(clock=FakeClock()), clock=clock)


async def test_positions_are_propagated_to_now_and_elements_cached() -> None:
    clock = FakeWallClock(EPOCH + timedelta(hours=3))
    stub = StubElements(ELEMENTS)
    service = space(stub, clock)
    first = await service.positions(SatelliteGroup.STATIONS)
    clock.now += timedelta(seconds=30)
    second = await service.positions(SatelliteGroup.STATIONS)
    assert stub.calls == 1
    iss_then = next(p for p in first if p.norad_id == 25544)
    iss_now = next(p for p in second if p.norad_id == 25544)
    assert iss_then.position != iss_now.position  # it moved in 30 s
    assert iss_now.at == clock.now
    assert iss_now.elements_age_days == 0.13
    assert -180 <= iss_now.position.lon < 180


async def test_stale_elements_are_not_plotted() -> None:
    stub = StubElements(ELEMENTS)
    positions = await space(stub, FakeWallClock(EPOCH + timedelta(days=40))).positions(
        SatelliteGroup.STATIONS
    )
    assert positions == []


async def test_decayed_objects_are_skipped() -> None:
    doomed = ELEMENTS[0].model_copy(
        update={"norad_id": 1, "mean_motion_rev_per_day": 17.5, "bstar": 0.5}
    )
    positions = await space(
        StubElements([doomed, ELEMENTS[1]]), FakeWallClock(EPOCH + timedelta(days=20))
    ).positions(SatelliteGroup.STATIONS)
    assert 1 not in {p.norad_id for p in positions}


async def test_maritime_sorts_by_recency_and_limits() -> None:
    now = EPOCH
    store = VesselStore(clock=FakeWallClock(now))
    for i, minutes in enumerate((5, 1, 3)):
        store.apply(
            PositionUpdate(
                f"10000000{i}", 1.0, 1.0, None, None, None, None, now - timedelta(minutes=minutes)
            )
        )
    registry = ProviderRegistry()
    registry.register(VESSEL_POSITIONS, VesselStoreFetcher(store, AisStreamRelay("k", store)))
    page = await MaritimeService(registry).vessels(VesselQuery(), limit=2)
    assert [v.mmsi for v in page.items] == ["100000001", "100000002"]
    assert page.truncated is True


async def test_celestrak_refusal_serves_last_known_elements() -> None:
    from argus.providers.errors import ProviderResponseError

    clock = FakeWallClock(EPOCH + timedelta(hours=1))
    cache_clock = FakeClock()
    stub = StubElements(ELEMENTS)
    registry = ProviderRegistry()
    registry.register(ORBITAL_ELEMENTS, stub)
    service = SpaceService(registry, InMemoryTTLCache(clock=cache_clock), clock=clock)

    assert await service.positions(SatelliteGroup.STATIONS)

    def refuse(query: ElementsQuery, raw: Any) -> list[OrbitalElements]:
        raise ProviderResponseError("celestrak", "HTTP 403")

    stub.transform = refuse  # type: ignore[method-assign]
    cache_clock.advance(3 * 3600)  # fresh entry expired, upstream now refuses
    assert await service.positions(SatelliteGroup.STATIONS)
