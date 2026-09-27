"""Tracks, launches, air alerts, facilities, cables and radar against recorded payloads."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.adsblol import AdsbLolTraceFetcher
from argus.adapters.adsblol.trace import downsample
from argus.adapters.launchlibrary import LaunchLibraryFetcher
from argus.adapters.opensky import OpenSkyTrackFetcher
from argus.adapters.overpass import OverpassFacilityFetcher, build_query
from argus.adapters.rainviewer import RainViewerRadarFetcher
from argus.adapters.telegeography import ATTRIBUTION, TeleGeographyCableFetcher
from argus.adapters.ukraine_alerts import REGIONS, UkraineAlertsFetcher
from argus.domain.aviation import TrackQuery
from argus.domain.events import EventCategory, EventQuery
from argus.domain.geo import BoundingBox
from argus.domain.imagery import RadarQuery
from argus.domain.infrastructure import CableQuery, FacilityKind, FacilityQuery
from argus.providers.errors import ProviderResponseError, UnsupportedQueryError
from tests.fakes import FakeWallClock, StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"
NOW = datetime(2026, 9, 27, 16, 30, tzinfo=UTC)


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


class TestTracks:
    async def test_adsblol_trace(self) -> None:
        raw = load("adsblol_trace.json")
        http = StubHttp(raw)
        track = await AdsbLolTraceFetcher(http, "https://t.test/traces").fetch(
            TrackQuery(icao24="ae2691")
        )
        assert http.calls[0][0] == "https://t.test/traces/91/trace_full_ae2691.json"
        assert track.callsign == "C6559"
        assert len(track.points) == 8
        first = track.points[0]
        assert first.at == datetime.fromtimestamp(raw["timestamp"] + raw["trace"][0][0], tz=UTC)
        assert first.altitude_m == pytest.approx(175 * 0.3048, abs=0.1)
        assert first.velocity_ms == pytest.approx(53.9 * 1852 / 3600, abs=0.01)
        assert track.points[2].on_ground is True
        assert track.points[2].altitude_m is None
        assert [p.at for p in track.points] == sorted(p.at for p in track.points)

    @pytest.mark.parametrize("raw", [None, {"trace": []}, {"timestamp": 1}])
    def test_adsblol_bad_payload(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            AdsbLolTraceFetcher(StubHttp()).transform(TrackQuery(icao24="abc123"), raw)

    async def test_opensky_track(self) -> None:
        http = StubHttp(load("opensky_track.json"))
        track = await OpenSkyTrackFetcher(http, "https://os.test/api").fetch(
            TrackQuery(icao24="3c6444")
        )
        assert http.calls[0] == (
            "https://os.test/api/tracks/all",
            {"icao24": "3c6444", "time": "0"},
        )
        assert track.callsign == "DLH6CJ"
        assert len(track.points) == 6
        assert track.points[0].altitude_m == 2133

    def test_opensky_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            OpenSkyTrackFetcher(StubHttp()).transform(TrackQuery(icao24="abc123"), {"icao24": "x"})

    def test_icao_is_validated(self) -> None:
        with pytest.raises(ValueError, match="pattern"):
            TrackQuery(icao24="nothex")

    def test_downsample_keeps_bounds_and_size(self) -> None:
        items = list(range(10_000))
        thinned = downsample(items, 2_000)
        assert len(thinned) == 2_000
        assert thinned[0] == 0
        assert thinned[-1] == 9_999
        assert downsample([1, 2], 10) == [1, 2]


class TestLaunches:
    def test_query_asks_from_the_window_start(self) -> None:
        params = LaunchLibraryFetcher(StubHttp()).transform_query(
            EventQuery(since=NOW - timedelta(days=1))
        )
        assert params == {
            "net__gte": "2026-09-26T16:30:00Z",
            "ordering": "net",
            "limit": "50",
            "mode": "normal",
        }

    async def test_parses_launches_at_their_pad(self) -> None:
        http = StubHttp(load("ll2_upcoming.json"))
        events = await LaunchLibraryFetcher(http, token="T").fetch(EventQuery(since=NOW))
        assert len(events) == 4  # the launch without pad coordinates is skipped
        first = events[0]
        assert first.category is EventCategory.LAUNCH
        assert first.id.startswith("ll2:")
        assert first.details["status"] is not None
        assert first.details["rocket"] is not None
        assert first.position.lat == pytest.approx(25.99677)

    def test_repr_hides_the_token(self) -> None:
        assert "T0KEN" not in repr(LaunchLibraryFetcher(StubHttp(), token="T0KEN"))

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            LaunchLibraryFetcher(StubHttp()).transform(
                EventQuery(since=NOW), {"detail": "throttled"}
            )


class TestUkraineAlerts:
    def fetcher(self) -> UkraineAlertsFetcher:
        return UkraineAlertsFetcher(StubHttp(), clock=FakeWallClock(NOW))

    def test_only_active_regions_become_events(self) -> None:
        raw = load("ubilling_alerts.json")
        events = self.fetcher().transform(EventQuery(since=NOW), raw)
        active = [name for name, state in raw["states"].items() if state["alertnow"]]
        assert len(events) == len(active)
        assert {e.category for e in events} == {EventCategory.AIR_RAID_ALERT}
        assert all(e.occurred_at == NOW for e in events)
        assert all("not a target" in str(e.details["placement"]) for e in events)

    def test_every_known_region_has_coordinates_inside_ukraine(self) -> None:
        for _, lat, lon in REGIONS.values():
            assert 44 <= lat <= 52.5
            assert 22 <= lon <= 40.5

    def test_implausible_start_times_are_reported_as_unknown(self) -> None:
        raw = {
            "states": {
                "Одеська область": {"alertnow": True, "changed": "1970-01-01 03:00:00"},
                "Львівська область": {"alertnow": True, "changed": "2026-09-27 18:00:00"},
            }
        }
        events = {
            e.details["region"]: e for e in self.fetcher().transform(EventQuery(since=NOW), raw)
        }
        assert events["Одеська область"].details["active_since"] is None
        assert events["Львівська область"].details["active_since"] == "2026-09-27T15:00:00+00:00"

    def test_unknown_regions_are_skipped(self) -> None:
        raw = {"states": {"Atlantis": {"alertnow": True}}}
        assert self.fetcher().transform(EventQuery(since=NOW), raw) == []

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            self.fetcher().transform(EventQuery(since=NOW), {"error": "x"})


class TestOverpass:
    box = BoundingBox(west=2.0, south=48.5, east=2.8, north=49.2)

    def test_query_language(self) -> None:
        q = build_query(FacilityQuery(kind=FacilityKind.NUCLEAR_PLANT, bbox=self.box))
        assert q.startswith("[out:json][timeout:80];(")
        assert 'nwr["plant:source"="nuclear"](48.5,2.0,49.2,2.8);' in q
        assert q.endswith("out center tags 2000;")

    def test_large_boxes_ask_to_zoom_in(self) -> None:
        huge = FacilityQuery(
            kind=FacilityKind.MILITARY, bbox=BoundingBox(west=0, south=40, east=10, north=50)
        )
        with pytest.raises(UnsupportedQueryError, match="max 25"):
            OverpassFacilityFetcher(StubHttp(), "https://o.test", "overpass-de").transform_query(
                huge
            )

    async def test_parses_nodes_and_centers(self) -> None:
        raw = load("overpass_facilities.json")
        raw["elements"].append(
            {
                "type": "way",
                "id": 7,
                "center": {"lat": 48.9, "lon": 2.5},
                "tags": {"military": "airfield"},
            }
        )
        raw["elements"].append({"type": "relation", "id": 8, "tags": {}})
        http = StubHttp(raw)
        fetcher = OverpassFacilityFetcher(http, "https://o.test/api", "overpass-kumi")
        facilities = await fetcher.fetch(
            FacilityQuery(kind=FacilityKind.DATA_CENTER, bbox=self.box)
        )
        assert fetcher.provider_name == "overpass-kumi"
        assert http.calls[0][0] == "https://o.test/api"
        assert facilities[0].name == "SFR Netcenter Courbevoie"
        assert facilities[0].url == "https://www.openstreetmap.org/node/2556825308"
        way = next(f for f in facilities if f.id == "osm:way/7")
        assert (way.position.lat, way.subtype) == (48.9, "airfield")
        assert "osm:relation/8" not in {f.id for f in facilities}

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            OverpassFacilityFetcher(StubHttp(), "u", "o").transform(
                FacilityQuery(kind=FacilityKind.MILITARY, bbox=self.box), "<html>"
            )


class TestCables:
    async def test_fetches_cables_and_landing_points(self) -> None:
        cables, points = load("cables.json"), load("landing_points.json")
        http = StubHttp(lambda url: cables if "cable-geo" in url else points)
        network = await TeleGeographyCableFetcher(http, "https://tg.test/api/v3").fetch(
            CableQuery()
        )
        assert {u for u, _ in http.calls} == {
            "https://tg.test/api/v3/cable/cable-geo.json",
            "https://tg.test/api/v3/landing-point/landing-point-geo.json",
        }
        assert len(network.cables) == 3
        assert len(network.landing_points) == 4
        assert network.attribution == ATTRIBUTION
        assert all(len(line) >= 2 for cable in network.cables for line in cable.lines)

    def test_linestring_and_degenerate_geometries(self) -> None:
        raw = {
            "cables": {
                "features": [
                    {
                        "properties": {"id": "a", "name": "A"},
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    },
                    {
                        "properties": {"id": "b", "name": "B"},
                        "geometry": {"type": "MultiLineString", "coordinates": [[[0, 0]]]},
                    },
                ]
            },
            "landing_points": {
                "features": [{"properties": {"id": "x"}, "geometry": {"coordinates": [0, 0]}}]
            },
        }
        network = TeleGeographyCableFetcher(StubHttp()).transform(CableQuery(), raw)
        assert [c.id for c in network.cables] == ["a"]
        assert network.landing_points == ()

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            TeleGeographyCableFetcher(StubHttp()).transform(
                CableQuery(), {"cables": {}, "landing_points": {}}
            )


class TestRadar:
    async def test_latest_frame_becomes_a_tile_layer(self) -> None:
        raw = load("rainviewer.json")
        layer = await RainViewerRadarFetcher(StubHttp(raw)).fetch(RadarQuery())
        latest = raw["radar"]["past"][-1]
        assert layer.tiles == (f"{raw['host']}{latest['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",)
        assert layer.valid_at == datetime.fromtimestamp(latest["time"], tz=UTC)
        assert layer.max_zoom == 7

    def test_no_frames(self) -> None:
        with pytest.raises(ProviderResponseError):
            RainViewerRadarFetcher(StubHttp()).transform(
                RadarQuery(), {"host": "h", "radar": {"past": []}}
            )
