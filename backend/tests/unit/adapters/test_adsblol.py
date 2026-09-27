import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.adsblol import AdsbLolAircraftFetcher, AdsbLolMilitaryFetcher
from argus.adapters.readsb import parse_aircraft
from argus.domain.aviation import AircraftQuery
from argus.domain.geo import BoundingBox, covering_circle, haversine_nm
from argus.providers.errors import ProviderResponseError, UnsupportedQueryError
from tests.fakes import StubHttp

FIXTURE = Path(__file__).parents[2] / "fixtures" / "adsblol_mil.json"
NOW = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


@pytest.fixture
def payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


class TestReadsbParser:
    def test_converts_aviation_units_to_si(self) -> None:
        record = {
            "hex": "AE2691",
            "flight": "C6559   ",
            "r": "6559",
            "t": "AS65",
            "alt_baro": 1000,
            "alt_geom": 1100,
            "gs": 100,
            "track": 370,
            "geom_rate": 600,
            "squawk": "1200",
            "lat": 38.2,
            "lon": -122.3,
            "seen_pos": 2.5,
        }
        a = parse_aircraft(record, now=NOW, source="adsblol")
        assert a is not None
        assert a.icao24 == "ae2691"
        assert (a.callsign, a.registration, a.type_code, a.squawk) == (
            "C6559",
            "6559",
            "AS65",
            "1200",
        )
        assert a.altitude_m == pytest.approx(335.3, abs=0.1)  # geometric preferred
        assert a.velocity_ms == pytest.approx(51.44, abs=0.01)
        assert a.vertical_rate_ms == pytest.approx(3.05, abs=0.01)
        assert a.heading_deg == 10
        assert a.last_contact == datetime(2026, 9, 27, 15, 59, 57, 500000, tzinfo=UTC)

    def test_ground_string_means_on_ground_with_unknown_altitude(self) -> None:
        a = parse_aircraft(
            {"hex": "abc123", "alt_baro": "ground", "lat": 1, "lon": 2}, now=NOW, source="x"
        )
        assert a is not None
        assert a.on_ground is True
        assert a.altitude_m is None

    def test_non_icao_marker_is_stripped(self) -> None:
        a = parse_aircraft({"hex": "~abc123", "lat": 1, "lon": 2}, now=NOW, source="x")
        assert a is not None
        assert a.icao24 == "abc123"

    @pytest.mark.parametrize(
        "record",
        [
            {"hex": "abc123"},
            {"hex": "abc123", "lat": "1", "lon": 2},
            {"hex": "bad", "lat": 1, "lon": 2},
        ],
    )
    def test_unusable_records_are_skipped(self, record: dict[str, Any]) -> None:
        assert parse_aircraft(record, now=NOW, source="x") is None


class TestGeometry:
    def test_haversine_paris_london(self) -> None:
        assert haversine_nm(48.8566, 2.3522, 51.5074, -0.1278) == pytest.approx(185.6, abs=0.5)

    def test_covering_circle_contains_every_corner(self) -> None:
        box = BoundingBox(west=2.0, south=48.0, east=3.0, north=49.0)
        lat, lon, radius = covering_circle(box)
        assert (lat, lon) == (48.5, 2.5)
        for corner in ((48, 2), (48, 3), (49, 2), (49, 3)):
            assert haversine_nm(lat, lon, *corner) <= radius + 1e-9


class TestAircraftFetcher:
    def test_small_box_becomes_a_point_query(self) -> None:
        box = BoundingBox(west=2.0, south=48.5, east=2.8, north=49.1)
        params = AdsbLolAircraftFetcher(StubHttp()).transform_query(AircraftQuery(bbox=box))
        assert params == {"lat": "48.8000", "lon": "2.4000", "radius": "25"}

    @pytest.mark.parametrize(
        "query",
        [AircraftQuery(), AircraftQuery(bbox=BoundingBox(west=-20, south=30, east=40, north=70))],
    )
    def test_world_or_huge_boxes_are_out_of_scope(self, query: AircraftQuery) -> None:
        with pytest.raises(UnsupportedQueryError):
            AdsbLolAircraftFetcher(StubHttp()).transform_query(query)

    async def test_fetch_uses_point_endpoint(self, payload: dict[str, Any]) -> None:
        http = StubHttp(payload)
        box = BoundingBox(west=2.0, south=48.5, east=2.8, north=49.1)
        await AdsbLolAircraftFetcher(http, "https://adsb.test/").fetch(AircraftQuery(bbox=box))
        assert http.calls[0][0] == "https://adsb.test/v2/point/48.8000/2.4000/25"


class TestMilitaryFetcher:
    async def test_parses_positioned_aircraft_only(self, payload: dict[str, Any]) -> None:
        http = StubHttp(payload)
        aircraft = await AdsbLolMilitaryFetcher(http, "https://adsb.test").fetch(AircraftQuery())
        assert http.calls[0][0] == "https://adsb.test/v2/mil"
        assert len(aircraft) == 4  # the record without a position is dropped
        assert {a.source for a in aircraft} == {"adsblol"}
        assert any(a.on_ground for a in aircraft)
        expected_now = datetime.fromtimestamp(payload["now"] / 1000, tz=UTC)
        assert all(a.last_contact <= expected_now for a in aircraft)

    def test_rejects_payload_without_ac(self) -> None:
        with pytest.raises(ProviderResponseError):
            AdsbLolMilitaryFetcher(StubHttp()).transform(AircraftQuery(), {"msg": "nope"})

    def test_missing_now_falls_back_to_system_time(self) -> None:
        aircraft = AdsbLolMilitaryFetcher(StubHttp()).transform(
            AircraftQuery(), {"ac": [{"hex": "abc123", "lat": 1, "lon": 2}]}
        )
        assert aircraft[0].last_contact.tzinfo is not None
