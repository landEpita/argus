import json
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.opensky import OpenSkyAircraftFetcher
from argus.domain.aviation import AircraftQuery
from argus.domain.geo import BoundingBox
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.fakes import StubHttp

FIXTURE = Path(__file__).parents[2] / "fixtures" / "opensky_states.json"


@pytest.fixture
def payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


def fetcher(http: StubHttp) -> OpenSkyAircraftFetcher:
    return OpenSkyAircraftFetcher(http, base_url="https://opensky.test/api/")


class TestQuery:
    def test_bbox_maps_to_opensky_params(self) -> None:
        query = AircraftQuery(bbox=BoundingBox(west=2.0, south=48.5, east=2.8, north=49.1))
        assert fetcher(StubHttp()).transform_query(query) == {
            "lamin": "48.5",
            "lomin": "2.0",
            "lamax": "49.1",
            "lomax": "2.8",
        }

    def test_no_bbox_means_whole_world(self) -> None:
        assert fetcher(StubHttp()).transform_query(AircraftQuery()) == {}


class TestTransform:
    def test_parses_usable_rows_and_skips_the_rest(self, payload: dict[str, Any]) -> None:
        aircraft = fetcher(StubHttp()).transform(AircraftQuery(), payload)
        assert [a.icao24 for a in aircraft] == ["3c6444", "39de4f", "3950c1"]

    def test_maps_columns_by_name_not_position_guesswork(self, payload: dict[str, Any]) -> None:
        first = fetcher(StubHttp()).transform(AircraftQuery(), payload)[0]
        assert first.callsign == "DLH9LF"
        assert first.origin_country == "Germany"
        assert (first.position.lat, first.position.lon) == (49.0097, 2.5471)
        assert first.altitude_m == 11277.6  # geometric altitude preferred over barometric
        assert first.velocity_ms == 231.4
        assert first.heading_deg == 87.2
        assert first.on_ground is False
        assert first.source == "opensky"

    def test_ground_flag_and_empty_callsign(self, payload: dict[str, Any]) -> None:
        grounded = fetcher(StubHttp()).transform(AircraftQuery(), payload)[2]
        assert grounded.on_ground is True
        assert grounded.callsign is None

    def test_missing_altitudes_stay_unknown(self, payload: dict[str, Any]) -> None:
        second = fetcher(StubHttp()).transform(AircraftQuery(), payload)[1]
        assert second.altitude_m is None

    def test_falls_back_to_barometric_altitude(self, payload: dict[str, Any]) -> None:
        row = list(payload["states"][0])
        row[13] = None
        [aircraft] = fetcher(StubHttp()).transform(AircraftQuery(), {"states": [row]})
        assert aircraft.altitude_m == 10972.8

    def test_null_states_means_empty_sky(self) -> None:
        assert fetcher(StubHttp()).transform(AircraftQuery(), {"time": 1, "states": None}) == []

    @pytest.mark.parametrize("raw", [None, [], {"time": 1}, {"states": "nope"}])
    def test_unusable_payload_raises(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            fetcher(StubHttp()).transform(AircraftQuery(), raw)


async def test_fetch_calls_states_endpoint(payload: dict[str, Any]) -> None:
    http = StubHttp(payload)
    query = AircraftQuery(bbox=BoundingBox(west=2.0, south=48.5, east=2.8, north=49.1))
    aircraft = await fetcher(http).fetch(query)
    assert len(aircraft) == 3
    [(url, params)] = http.calls
    assert url == "https://opensky.test/api/states/all"
    assert params["lamin"] == "48.5"


async def test_fetch_propagates_provider_errors() -> None:
    http = StubHttp(error=ProviderUnavailableError("opensky", "HTTP 429"))
    with pytest.raises(ProviderUnavailableError):
        await fetcher(http).fetch(AircraftQuery())
