from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from argus.container import Container
from argus.domain.aviation import AIRCRAFT_TRACK, AircraftTrack, TrackPoint
from argus.domain.events import LAUNCHES, EventCategory, GeoEvent
from argus.domain.geo import GeoPoint
from argus.domain.infrastructure import (
    FACILITIES,
    SUBMARINE_CABLES,
    Cable,
    CableNetwork,
    Facility,
    FacilityKind,
    LandingPoint,
)
from argus.providers.errors import ProviderNotFoundError, ProviderUnavailableError
from tests.api.conftest import ClientFactory
from tests.unit.services.test_phase2b_services import Stub


def register(*pairs: tuple[Any, Any]) -> Callable[[Container], None]:
    def configure(container: Container) -> None:
        for capability, fetcher in pairs:
            container.registry.register(capability, fetcher)

    return configure


async def test_track(make_client: ClientFactory) -> None:
    track = AircraftTrack(
        icao24="abc123",
        callsign="AFR1",
        points=(TrackPoint(at=datetime(2026, 9, 27, tzinfo=UTC), position=GeoPoint(lat=1, lon=2)),),
        source="adsblol",
    )
    client = await make_client(configure=register((AIRCRAFT_TRACK, Stub(track))))
    body = (await client.get("/api/v1/aviation/aircraft/ABC123/track")).json()
    assert body["icao24"] == "abc123"
    assert body["points"][0]["position"] == {"lat": 1.0, "lon": 2.0}
    assert (await client.get("/api/v1/aviation/aircraft/zzz/track")).status_code == 422


async def test_unknown_track_is_404_even_after_fallback(make_client: ClientFactory) -> None:
    client = await make_client(
        configure=register(
            (AIRCRAFT_TRACK, Stub(error=ProviderNotFoundError("adsblol", "HTTP 404"))),
            (AIRCRAFT_TRACK, Stub(error=ProviderNotFoundError("opensky", "HTTP 404"))),
        )
    )
    response = await client.get("/api/v1/aviation/aircraft/abc123/track")
    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "capability": "aviation.aircraft_track"}


async def test_mixed_not_found_and_outage_is_503(make_client: ClientFactory) -> None:
    client = await make_client(
        configure=register(
            (AIRCRAFT_TRACK, Stub(error=ProviderNotFoundError("adsblol", "HTTP 404"))),
            (AIRCRAFT_TRACK, Stub(error=ProviderUnavailableError("opensky", "timeout"))),
        )
    )
    assert (await client.get("/api/v1/aviation/aircraft/abc123/track")).status_code == 503


async def test_launches_include_the_future(make_client: ClientFactory) -> None:
    launch = GeoEvent(
        id="ll2:1",
        category=EventCategory.LAUNCH,
        title="Falcon 9",
        position=GeoPoint(lat=28.5, lon=-80.6),
        occurred_at=datetime.now(UTC) + timedelta(days=2),
        source="launchlibrary",
    )
    client = await make_client(configure=register((LAUNCHES, Stub([launch]))))
    body = (await client.get("/api/v1/events/launches", params={"since_hours": 24})).json()
    assert [e["id"] for e in body["items"]] == ["ll2:1"]


async def test_facilities_need_a_bbox(make_client: ClientFactory) -> None:
    item = Facility(
        id="osm:node/1",
        kind=FacilityKind.DATA_CENTER,
        position=GeoPoint(lat=48.9, lon=2.3),
        source="s",
    )
    client = await make_client(configure=register((FACILITIES, Stub([item]))))
    assert (await client.get("/api/v1/infrastructure/facilities/data-center")).status_code == 422
    body = (
        await client.get(
            "/api/v1/infrastructure/facilities/data-center", params={"bbox": "2,48,3,49"}
        )
    ).json()
    assert body["count"] == 1
    assert (
        await client.get("/api/v1/infrastructure/facilities/castles", params={"bbox": "2,48,3,49"})
    ).status_code == 422


async def test_cables_are_gzipped(make_client: ClientFactory) -> None:
    network = CableNetwork(
        cables=tuple(
            Cable(id=f"c{i}", name=f"Cable {i}", lines=(((0.0, 0.0), (float(i), 1.0)),))
            for i in range(200)
        ),
        landing_points=(LandingPoint(id="p", name="P", position=GeoPoint(lat=0, lon=0)),),
        source="telegeography",
        attribution="© TeleGeography",
    )
    client = await make_client(configure=register((SUBMARINE_CABLES, Stub(network))))
    response = await client.get(
        "/api/v1/infrastructure/submarine-cables", headers={"Accept-Encoding": "gzip"}
    )
    assert response.headers["content-encoding"] == "gzip"
    assert len(response.json()["cables"]) == 200


async def test_rasters_listed_without_radar(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/imagery/rasters")).json()
    assert [layer["id"] for layer in body] == ["satellite-true-color", "night-lights"]
