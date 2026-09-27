from argus.domain.aviation import Aircraft, AircraftQuery
from argus.providers.errors import ProviderUnavailableError
from tests.api.conftest import ClientFactory
from tests.fakes import StubAircraftFetcher, make_aircraft

URL = "/api/v1/aviation/aircraft"
PARIS = "2.2,48.8,2.5,48.9"


def sky(_: AircraftQuery) -> list[Aircraft]:
    return [
        make_aircraft("aaaaa1", lat=48.85, lon=2.35),
        make_aircraft("aaaaa2", lat=48.85, lon=2.35, on_ground=True),
        make_aircraft("bbbbb1", lat=40.0, lon=-74.0),
    ]


def down(_: AircraftQuery) -> list[Aircraft]:
    raise ProviderUnavailableError("opensky", "HTTP 503")


async def test_lists_airborne_aircraft_in_bbox(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(sky))
    response = await client.get(URL, params={"bbox": PARIS})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["icao24"] == "aaaaa1"
    assert body["items"][0]["position"] == {"lat": 48.85, "lon": 2.35}


async def test_include_on_ground(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(sky))
    response = await client.get(URL, params={"bbox": PARIS, "include_on_ground": "true"})
    assert response.json()["count"] == 2


async def test_world_without_bbox(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(sky))
    assert (await client.get(URL)).json()["count"] == 2


async def test_invalid_bbox_is_422(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(sky))
    response = await client.get(URL, params={"bbox": "1,2,3"})
    assert response.status_code == 422
    assert "invalid bbox" in response.json()["detail"]


async def test_upstream_failure_is_503_and_names_the_provider(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(down, name="opensky"))
    response = await client.get(URL)
    assert response.status_code == 503
    assert response.json() == {
        "error": "upstream_unavailable",
        "capability": "aviation.aircraft_states",
        "providers": ["opensky"],
    }


async def test_fallback_provider_serves_when_primary_is_down(make_client: ClientFactory) -> None:
    client = await make_client(
        StubAircraftFetcher(down, name="opensky"), StubAircraftFetcher(sky, name="adsblol")
    )
    assert (await client.get(URL)).json()["count"] == 2


async def test_disabled_capability_is_503(make_client: ClientFactory) -> None:
    response = await (await make_client()).get(URL)
    assert response.status_code == 503
    assert response.json()["error"] == "capability_disabled"
