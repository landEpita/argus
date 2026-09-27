"""Military aircraft, events, satellites and vessels through HTTP."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from argus.adapters.celestrak import CelestrakElementsFetcher
from argus.container import Container
from argus.domain.aviation import MILITARY_AIRCRAFT, Aircraft, AircraftQuery
from argus.domain.events import EARTHQUAKES, EventCategory, GeoEvent
from argus.domain.geo import GeoPoint
from argus.domain.space import ORBITAL_ELEMENTS, ElementsQuery, SatelliteGroup
from argus.providers.errors import UnsupportedQueryError
from tests.api.conftest import ClientFactory
from tests.fakes import StubAircraftFetcher, StubHttp, make_aircraft

FIXTURES = Path(__file__).parents[1] / "fixtures"


def register(capability: Any, fetcher: Any) -> Callable[[Container], None]:
    def configure(container: Container) -> None:
        container.registry.register(capability, fetcher)

    return configure


async def test_military_endpoint(make_client: ClientFactory) -> None:
    fetcher = StubAircraftFetcher(lambda _: [make_aircraft("ae1234")], name="adsblol")
    client = await make_client(configure=register(MILITARY_AIRCRAFT, fetcher))
    body = (await client.get("/api/v1/aviation/military")).json()
    assert body["count"] == 1
    assert body["items"][0]["icao24"] == "ae1234"
    assert "type_code" in body["items"][0]


async def test_unsupported_query_is_422(make_client: ClientFactory) -> None:
    def out_of_scope(_: AircraftQuery) -> list[Aircraft]:
        raise UnsupportedQueryError("adsblol", "needs a bounding box")

    client = await make_client(StubAircraftFetcher(out_of_scope, name="adsblol"))
    response = await client.get("/api/v1/aviation/aircraft")
    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_query"


async def test_events_feed_listing_and_data(make_client: ClientFactory) -> None:
    from tests.unit.services.test_events import StubFeed

    now = datetime.now(UTC)
    quake = GeoEvent(
        id="usgs:1",
        category=EventCategory.EARTHQUAKE,
        title="M 6.1",
        position=GeoPoint(lat=35.7, lon=139.7),
        occurred_at=now - timedelta(hours=1),
        severity=0.68,
        magnitude=6.1,
        source="usgs",
    )
    client = await make_client(configure=register(EARTHQUAKES, StubFeed([quake])))

    feeds = {f["feed"]: f for f in (await client.get("/api/v1/events")).json()}
    assert feeds["earthquakes"] == {"feed": "earthquakes", "providers": ["stub"], "available": True}
    assert feeds["fires"]["available"] is False

    body = (await client.get("/api/v1/events/earthquakes", params={"since_hours": 6})).json()
    assert body["count"] == 1
    assert body["truncated"] is False
    assert body["items"][0]["category"] == "earthquake"
    assert body["items"][0]["details"] == {}


async def test_disabled_feed_is_503_and_unknown_feed_is_422(client: httpx.AsyncClient) -> None:
    disabled = await client.get("/api/v1/events/fires")
    assert disabled.status_code == 503
    assert disabled.json() == {"error": "capability_disabled", "capability": "events.fires"}
    assert (await client.get("/api/v1/events/aliens")).status_code == 422
    assert (
        await client.get("/api/v1/events/earthquakes", params={"since_hours": 0})
    ).status_code == 422


async def test_satellites(make_client: ClientFactory) -> None:
    raw = json.loads((FIXTURES / "celestrak_stations.json").read_text())
    # Epochs in the fixture are from today; a real fetcher over a stub HTTP client keeps it honest.
    fetcher = CelestrakElementsFetcher(StubHttp(raw))
    client = await make_client(configure=register(ORBITAL_ELEMENTS, fetcher))
    body = (await client.get("/api/v1/space/satellites", params={"group": "stations"})).json()
    assert body["group"] == "stations"
    elements = CelestrakElementsFetcher(StubHttp()).transform(
        ElementsQuery(group=SatelliteGroup.STATIONS), raw
    )
    fresh = [e for e in elements if abs((datetime.now(UTC) - e.epoch).days) <= 30]
    assert body["count"] == len(fresh)
    assert (
        await client.get("/api/v1/space/satellites", params={"group": "ufo"})
    ).status_code == 422


async def test_vessels_disabled_without_key(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/maritime/vessels")
    assert response.status_code == 503
    assert response.json()["capability"] == "maritime.vessel_positions"


async def test_vessels_served_from_the_relay_store(make_client: ClientFactory) -> None:
    from argus.adapters.aisstream.messages import PositionUpdate

    def enable_ais(container: Container) -> None:
        from argus.adapters.aisstream import AisStreamRelay, VesselStore, VesselStoreFetcher
        from argus.domain.maritime import VESSEL_POSITIONS

        store = VesselStore()
        store.apply(
            PositionUpdate("227006760", 43.3, 5.35, 6.0, 90.0, None, "MARIUS", datetime.now(UTC))
        )
        container.registry.register(
            VESSEL_POSITIONS, VesselStoreFetcher(store, AisStreamRelay("k", store))
        )

    client = await make_client(configure=enable_ais)
    body = (await client.get("/api/v1/maritime/vessels", params={"bbox": "5,43,6,44"})).json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "MARIUS"
    assert body["items"][0]["category"] == "unknown"


async def test_background_services_start_and_stop_with_the_app() -> None:
    from argus.main import create_app
    from tests.conftest import offline_settings

    settings = offline_settings(aisstream_api_key=SecretStr("k"))
    app = create_app(settings)
    container: Container = app.state.container
    relay = next(s for s in container.background if s.name == "aisstream-relay")
    started: list[str] = []

    async def fake_start() -> None:
        started.append("start")

    async def fake_stop() -> None:
        started.append("stop")

    relay.start = fake_start  # type: ignore[method-assign]
    relay.stop = fake_stop  # type: ignore[method-assign]
    async with app.router.lifespan_context(app):
        assert started == ["start"]
    assert started == ["start", "stop"]
