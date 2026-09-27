from typing import Any

from argus.domain.cameras import CAMERAS, Camera, CameraNetwork, FeedKind
from argus.domain.geo import BoundingBox, GeoPoint
from argus.infra.cache import InMemoryTTLCache
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderUnavailableError
from argus.providers.registry import ProviderRegistry
from argus.services.cameras import CameraService
from tests.fakes import FakeClock

LONDON = BoundingBox(west=-0.3, south=51.4, east=0.1, north=51.6)


def cam(i: str, network: CameraNetwork, lat: float, lon: float) -> Camera:
    return Camera(
        id=f"{network.value}:{i}", network=network, name=i, position=GeoPoint(lat=lat, lon=lon),
        feed=FeedKind.IMAGE, url="https://x.test/a.jpg", source=network.value,
    )  # fmt: skip


class Catalog(Fetcher[Any, list[Camera]]):
    def __init__(self, name: str, cameras: list[Camera]) -> None:
        self.provider_name = name
        self.cameras = cameras
        self.fail = False
        self.calls = 0

    async def extract(self, params: Any) -> Any:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailableError(self.provider_name, "HTTP 503")

    def transform(self, query: Any, raw: Any) -> list[Camera]:
        return self.cameras


def setup() -> tuple[CameraService, Catalog, Catalog]:
    registry = ProviderRegistry()
    tfl = Catalog(
        "tfl", [cam("a", CameraNetwork.TFL, 51.5, -0.1), cam("b", CameraNetwork.TFL, 51.3, -0.5)]
    )
    nsw = Catalog("nsw", [cam("c", CameraNetwork.NSW, -33.9, 151.2)])
    registry.register(CAMERAS[CameraNetwork.TFL], tfl, priority=10)
    registry.register(CAMERAS[CameraNetwork.NSW], nsw, priority=10)
    return CameraService(registry, InMemoryTTLCache(clock=FakeClock())), tfl, nsw


async def test_only_networks_overlapping_the_view_are_read() -> None:
    service, tfl, nsw = setup()
    view = await service.cameras(LONDON)
    assert [c.id for c in view.items] == ["tfl:a"]
    assert (view.networks, view.unavailable) == ([CameraNetwork.TFL], [])
    assert nsw.calls == 0
    await service.cameras(BoundingBox(west=-1, south=51, east=1, north=52))
    assert tfl.calls == 1  # one catalog serves every view


async def test_a_failing_or_unregistered_network_is_reported_not_hidden() -> None:
    service, _, nsw = setup()
    nsw.fail = True
    view = await service.cameras(None)
    assert {c.id for c in view.items} == {"tfl:a", "tfl:b"}
    assert CameraNetwork.NSW in view.unavailable
    assert CameraNetwork.DRIVEBC in view.unavailable  # no fetcher registered
    only = await service.cameras(None, {CameraNetwork.TFL})
    assert only.networks == [CameraNetwork.TFL]
