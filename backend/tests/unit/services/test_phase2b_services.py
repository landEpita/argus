from datetime import UTC, datetime
from typing import Any

import pytest

from argus.domain.geo import BoundingBox, GeoPoint
from argus.domain.imagery import WEATHER_RADAR, RadarQuery, RasterLayer
from argus.domain.infrastructure import (
    FACILITIES,
    SUBMARINE_CABLES,
    CableNetwork,
    CableQuery,
    Facility,
    FacilityKind,
    FacilityQuery,
)
from argus.infra.cache import InMemoryTTLCache
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderUnavailableError
from argus.providers.registry import ProviderRegistry
from argus.services.imagery import ImageryService, gibs_layers
from argus.services.infrastructure import InfrastructureService, TooManyTilesError, tiles_for
from tests.fakes import FakeClock, FakeWallClock

NOW = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


class Stub(Fetcher[Any, Any]):
    provider_name = "stub"

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.queries: list[Any] = []

    async def extract(self, params: Any) -> Any:
        return None

    def transform(self, query: Any, raw: Any) -> Any:
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.result


def facility(i: str, lat: float, lon: float) -> Facility:
    return Facility(
        id=i, kind=FacilityKind.MILITARY, position=GeoPoint(lat=lat, lon=lon), source="stub"
    )


async def test_facilities_are_fetched_per_fixed_tile_and_filtered_exactly() -> None:
    stub = Stub([facility("in", 48.9, 2.4), facility("out", 48.1, 2.9)])
    registry = ProviderRegistry()
    registry.register(FACILITIES, stub)
    service = InfrastructureService(registry, InMemoryTTLCache(clock=FakeClock()))
    found = await service.facilities(
        FacilityKind.MILITARY, BoundingBox(west=2.2, south=48.7, east=2.6, north=49.0)
    )
    await service.facilities(
        FacilityKind.MILITARY, BoundingBox(west=1.3, south=46.8, east=4.5, north=49.9)
    )
    assert [f.id for f in found] == ["in"]
    assert len(stub.queries) == 1  # both views fall in the same 5 degree tile
    upstream: FacilityQuery = stub.queries[0]
    assert upstream.bbox == BoundingBox(west=0, south=45, east=5, north=50)


def test_tiles_cover_the_box_on_a_fixed_grid() -> None:
    tiles = tiles_for(BoundingBox(west=-2.5, south=48.0, east=7.0, north=51.0))
    assert {(t.west, t.south) for t in tiles} == {
        (-5, 45),
        (-5, 50),
        (0, 45),
        (0, 50),
        (5, 45),
        (5, 50),
    }
    assert len(tiles_for(BoundingBox(west=175, south=85, east=180, north=90))) == 1


async def test_too_wide_views_ask_to_zoom_in() -> None:
    service = InfrastructureService(ProviderRegistry(), InMemoryTTLCache())
    with pytest.raises(TooManyTilesError, match="zoom in"):
        await service.facilities(
            FacilityKind.MILITARY, BoundingBox(west=-30, south=20, east=40, north=70)
        )


async def test_tile_edges_do_not_duplicate() -> None:
    registry = ProviderRegistry()
    registry.register(FACILITIES, Stub([facility("edge", 50.0, 5.0)]))
    service = InfrastructureService(registry, InMemoryTTLCache(clock=FakeClock()))
    found = await service.facilities(
        FacilityKind.MILITARY, BoundingBox(west=3, south=48, east=7, north=52)
    )
    assert [f.id for f in found] == ["edge"]


async def test_cables_fall_back_to_last_good_copy() -> None:
    network = CableNetwork(cables=(), landing_points=(), source="stub", attribution="x")
    stub = Stub(network)
    registry = ProviderRegistry()
    registry.register(SUBMARINE_CABLES, stub)
    clock = FakeClock()
    service = InfrastructureService(registry, InMemoryTTLCache(clock=clock))
    assert await service.cables() == network
    stub.error = ProviderUnavailableError("stub", "down")
    clock.advance(2 * 86400)
    assert await service.cables() == network
    assert isinstance(stub.queries[-1], CableQuery)


def test_gibs_layers_use_the_given_day() -> None:
    layers = gibs_layers(NOW)
    assert [layer.id for layer in layers] == ["satellite-true-color", "night-lights"]
    assert all("/2026-09-27/" in layer.tiles[0] for layer in layers)
    assert all("{z}/{y}/{x}" in layer.tiles[0] for layer in layers)  # WMTS row/column order


@pytest.mark.parametrize("radar_works", [True, False])
async def test_imagery_lists_gibs_even_when_radar_fails(radar_works: bool) -> None:
    radar = RasterLayer(
        id="weather-radar", label="Radar", tiles=("t",), max_zoom=7, attribution="r"
    )
    registry = ProviderRegistry()
    registry.register(
        WEATHER_RADAR, Stub(radar, None if radar_works else ProviderUnavailableError("s", "x"))
    )
    service = ImageryService(
        registry, InMemoryTTLCache(clock=FakeClock()), clock=FakeWallClock(NOW)
    )
    ids = [layer.id for layer in await service.layers()]
    assert ids == (["weather-radar"] if radar_works else []) + [
        "satellite-true-color",
        "night-lights",
    ]
    assert all(
        "/2026-09-26/" in layer.tiles[0]
        for layer in (await service.layers())
        if layer.id != "weather-radar"
    )


async def test_imagery_without_radar_provider() -> None:
    service = ImageryService(ProviderRegistry(), InMemoryTTLCache(), clock=FakeWallClock(NOW))
    assert len(await service.layers()) == 2
    assert RadarQuery() == RadarQuery()
