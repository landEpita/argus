from pydantic import SecretStr

from argus.container import build_container
from argus.infra.cache import CACHE_SCHEMA_VERSION, InMemoryTTLCache, RedisCache
from tests.conftest import offline_settings
from tests.fakes import StubHttp

ALL_ON = {
    "opensky_enabled": True,
    "adsblol_enabled": True,
    "usgs_enabled": True,
    "eonet_enabled": True,
    "gdacs_enabled": True,
    "gdelt_enabled": True,
    "celestrak_enabled": True,
    "ukraine_alerts_enabled": True,
    "launchlibrary_enabled": True,
    "overpass_enabled": True,
    "telegeography_enabled": True,
    "rainviewer_enabled": True,
    "cameras_enabled": True,
}


async def test_keyless_providers_are_registered_in_fallback_order() -> None:
    container = build_container(offline_settings(**ALL_ON), http=StubHttp())
    assert container.registry.capabilities() == {
        "aviation.aircraft_states": ["adsblol", "opensky"],
        "aviation.aircraft_track": ["adsblol", "opensky"],
        "aviation.military_aircraft": ["adsblol"],
        "events.earthquakes": ["usgs"],
        "events.natural-events": ["eonet"],
        "events.disaster-alerts": ["gdacs"],
        "events.conflict": ["gdelt"],
        "events.air-alerts": ["ubilling"],
        "events.launches": ["launchlibrary"],
        "space.orbital_elements": ["celestrak"],
        "infrastructure.facilities": ["overpass-de", "overpass-kumi", "overpass-coffee"],
        "infrastructure.submarine_cables": ["telegeography"],
        "imagery.weather_radar": ["rainviewer"],
        **{f"cameras.{n}": [n] for n in ("tfl", "fintraffic", "drivebc", "nsw", "deldot")},
    }
    assert [s.name for s in container.background] == ["signal-snapshotter"]
    assert isinstance(container.cache, InMemoryTTLCache)
    assert set(container.readiness) == {"database"}
    await container.aclose()


async def test_keys_enable_fires_and_vessels() -> None:
    container = build_container(
        offline_settings(firms_map_key=SecretStr("k"), aisstream_api_key=SecretStr("k")),
        http=StubHttp(),
    )
    capabilities = container.registry.capabilities()
    assert capabilities["events.fires"] == ["firms"]
    assert capabilities["maritime.vessel_positions"] == ["aisstream"]
    assert [s.name for s in container.background] == ["aisstream-relay", "signal-snapshotter"]
    await container.aclose()


async def test_everything_can_be_disabled_and_http_is_closed() -> None:
    http = StubHttp()
    container = build_container(offline_settings(), http=http)
    assert container.registry.capabilities() == {}
    await container.aclose()
    assert http.closed


async def test_redis_url_selects_the_redis_cache_and_its_readiness_check() -> None:
    container = build_container(
        offline_settings(redis_url="redis://localhost:6399/0"), http=StubHttp()
    )
    assert isinstance(container.cache, RedisCache)
    assert container.cache._namespace == f"argus:v{CACHE_SCHEMA_VERSION}"
    assert set(container.readiness) == {"database", "cache"}
    assert "redis" in {s.source for s in container.health.snapshot()}
    await container.aclose()


async def test_opensky_credentials_enable_authenticated_fetchers() -> None:
    from argus.adapters.opensky.auth import AUTH_ENDPOINT
    from argus.domain.aviation import AIRCRAFT_STATES, AircraftQuery

    http = StubHttp({"access_token": "t", "expires_in": 1800, "states": []})
    container = build_container(
        offline_settings(
            opensky_enabled=True, opensky_client_id="me", opensky_client_secret=SecretStr("s")
        ),
        http=http,
    )
    await container.registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert http.calls[0][0] == AUTH_ENDPOINT
    assert http.calls[0][1]["client_id"] == "me"
    await container.aclose()
