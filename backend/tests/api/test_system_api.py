import re

import httpx

from argus import __version__
from argus.container import Container
from argus.domain.aviation import Aircraft, AircraftQuery
from argus.providers.errors import ProviderUnavailableError
from tests.api.conftest import ClientFactory
from tests.fakes import StubAircraftFetcher


def empty(_: AircraftQuery) -> list[Aircraft]:
    return []


def down(_: AircraftQuery) -> list[Aircraft]:
    raise ProviderUnavailableError("opensky", "timeout")


async def test_health_starts_idle(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(empty, name="opensky"))
    body = (await client.get("/api/v1/system/health")).json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["sources"] == [
        {
            "source": "opensky",
            "status": "idle",
            "last_success_age_s": None,
            "last_error": None,
            "consecutive_failures": 0,
        }
    ]


async def test_health_reflects_real_traffic(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(down, name="opensky"))
    await client.get("/api/v1/aviation/aircraft")
    body = (await client.get("/api/v1/system/health")).json()
    assert body["status"] == "failing"
    assert body["sources"][0]["last_error"] == "[opensky] timeout"


async def test_ready_probes_the_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/ready")
    assert response.status_code == 200
    assert response.json() == {"ready": True, "checks": {"database": "ok"}}


async def test_ready_is_503_when_a_dependency_fails(make_client: ClientFactory) -> None:
    async def broken() -> None:
        raise ConnectionError("db down")

    def break_database(container: Container) -> None:
        container.readiness["database"] = broken

    client = await make_client(configure=break_database)
    response = await client.get("/api/v1/system/ready")
    assert response.status_code == 503
    assert response.json() == {"ready": False, "checks": {"database": "error: ConnectionError"}}


async def test_capabilities(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(empty, name="opensky"))
    response = await client.get("/api/v1/system/capabilities")
    assert response.json() == {"aviation.aircraft_states": ["opensky"]}


async def test_metrics_count_requests_by_route_template(make_client: ClientFactory) -> None:
    client = await make_client(StubAircraftFetcher(empty, name="opensky"))
    await client.get("/api/v1/aviation/aircraft")
    await client.get("/api/v1/watchlists/00000000-0000-0000-0000-000000000000")
    text = (await client.get("/metrics")).text
    assert (
        'argus_http_requests_total{method="GET",route="/api/v1/aviation/aircraft",status="200"} 1.0'
        in text
    )
    assert 'route="/api/v1/watchlists/{watchlist_id}",status="404"' in text
    assert (
        'argus_provider_requests_total{capability="aviation.aircraft_states",'
        'outcome="success",provider="opensky"} 1.0' in text
    )


async def test_request_id_is_generated_or_propagated(client: httpx.AsyncClient) -> None:
    generated = await client.get("/api/v1/system/capabilities")
    assert re.fullmatch(r"[0-9a-f]{32}", generated.headers["x-request-id"])

    propagated = await client.get("/api/v1/system/capabilities", headers={"X-Request-ID": "abc-1"})
    assert propagated.headers["x-request-id"] == "abc-1"

    rejected = await client.get("/api/v1/system/capabilities", headers={"X-Request-ID": "bad id!"})
    assert rejected.headers["x-request-id"] != "bad id!"


async def test_openapi_is_served(client: httpx.AsyncClient) -> None:
    assert (await client.get("/openapi.json")).json()["info"]["title"] == "Argus API"


async def test_unknown_urls_share_one_metric_series(client: httpx.AsyncClient) -> None:
    await client.get("/wp-admin.php")
    await client.get("/.env")
    text = (await client.get("/metrics")).text
    assert 'argus_http_requests_total{method="GET",route="unmatched",status="404"} 2.0' in text
