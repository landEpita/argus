"""USGS, EONET, GDACS and FIRMS adapters against recorded payloads."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.eonet import EonetEventFetcher
from argus.adapters.firms import FirmsFireFetcher
from argus.adapters.gdacs import GdacsEventFetcher
from argus.adapters.usgs import UsgsEarthquakeFetcher
from argus.domain.events import EventCategory, EventQuery
from argus.domain.geo import BoundingBox
from argus.providers.errors import ProviderResponseError
from tests.fakes import FakeWallClock, StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"
NOW = datetime(2026, 9, 27, 16, 30, tzinfo=UTC)
CLOCK = FakeWallClock(NOW)


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def since(hours: float) -> EventQuery:
    return EventQuery(since=NOW - timedelta(hours=hours))


class TestUsgs:
    @pytest.mark.parametrize(
        ("hours", "feed"),
        [
            (0.5, "all_hour"),
            (24, "all_day"),
            (72, "2.5_week"),
            (24 * 20, "4.5_month"),
            (24 * 90, "4.5_month"),
        ],
    )
    def test_picks_the_smallest_covering_feed(self, hours: float, feed: str) -> None:
        fetcher = UsgsEarthquakeFetcher(StubHttp(), clock=CLOCK)
        assert fetcher.transform_query(since(hours)) == {"feed": feed}

    async def test_parses_features(self) -> None:
        http = StubHttp(load("usgs_all_day.json"))
        events = await UsgsEarthquakeFetcher(http, "https://usgs.test/", clock=CLOCK).fetch(
            since(24)
        )
        assert http.calls[0][0] == "https://usgs.test/all_day.geojson"
        assert len(events) == 5
        first = events[0]
        assert first.id.startswith("usgs:")
        assert first.category is EventCategory.EARTHQUAKE
        assert first.occurred_at.tzinfo is not None
        assert first.details["depth_km"] is not None

    def test_severity_scales_with_magnitude_and_tolerates_missing(self) -> None:
        events = {
            e.id: e
            for e in UsgsEarthquakeFetcher(StubHttp(), clock=CLOCK).transform(
                since(24), load("usgs_all_day.json")
            )
        }
        assert events["usgs:big1"].severity == pytest.approx(0.9)
        assert events["usgs:big1"].details["tsunami_warning"] is True
        assert events["usgs:nomag1"].severity is None
        assert events["usgs:nomag1"].magnitude is None

    @pytest.mark.parametrize("raw", [None, {}, {"features": "x"}])
    def test_rejects_non_geojson(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            UsgsEarthquakeFetcher(StubHttp(), clock=CLOCK).transform(since(1), raw)

    def test_skips_malformed_features(self) -> None:
        raw = {"features": [{"id": "x", "properties": {}, "geometry": {"coordinates": [1, 2]}}]}
        assert UsgsEarthquakeFetcher(StubHttp(), clock=CLOCK).transform(since(1), raw) == []


class TestEonet:
    def test_query_uses_days_and_eonet_bbox_order(self) -> None:
        box = BoundingBox(west=-10, south=35, east=5, north=45)
        params = EonetEventFetcher(StubHttp(), clock=CLOCK).transform_query(
            EventQuery(bbox=box, since=NOW - timedelta(hours=30))
        )
        assert params == {
            "status": "open",
            "days": "2",
            "limit": "500",
            "bbox": "-10.0,45.0,5.0,35.0",
        }

    async def test_uses_the_latest_track_point_and_maps_categories(self) -> None:
        http = StubHttp(load("eonet_events.json"))
        events = {e.id: e for e in await EonetEventFetcher(http, clock=CLOCK).fetch(since(24 * 30))}
        storm = events["eonet:EONET_24811"]
        assert storm.category is EventCategory.SEVERE_STORM
        assert (storm.position.lat, storm.position.lon) == (14.2, -22.4)  # the later of two points
        assert storm.severity == pytest.approx(40 / 150)
        assert storm.details["track_points"] == 2
        assert storm.url is not None

    def test_polygons_are_reduced_to_their_centroid(self) -> None:
        events = {
            e.id: e
            for e in EonetEventFetcher(StubHttp(), clock=CLOCK).transform(
                since(24), load("eonet_events.json")
            )
        }
        fire = events["eonet:EONET_POLY"]
        assert fire.category is EventCategory.WILDFIRE
        assert fire.position.lat == pytest.approx(40.8)
        assert fire.position.lon == pytest.approx(10.8)
        assert fire.severity is None

    def test_rejects_payload_without_events(self) -> None:
        with pytest.raises(ProviderResponseError):
            EonetEventFetcher(StubHttp(), clock=CLOCK).transform(since(1), {"title": "x"})

    def test_skips_events_without_dated_geometry(self) -> None:
        raw = {"events": [{"id": "a", "geometry": [{"type": "Point", "coordinates": [1, 2]}]}]}
        assert EonetEventFetcher(StubHttp(), clock=CLOCK).transform(since(1), raw) == []


class TestGdacs:
    def test_query(self) -> None:
        params = GdacsEventFetcher(StubHttp()).transform_query(since(48))
        assert params["fromdate"] == "2026-09-25"
        assert params["alertlevel"] == "Green;Orange;Red"

    async def test_parses_alert_levels_and_types(self) -> None:
        http = StubHttp(load("gdacs_events.json"))
        events = await GdacsEventFetcher(http, "https://gdacs.test/api").fetch(since(24 * 7))
        assert http.calls[0][0] == "https://gdacs.test/api/events/geteventlist/SEARCH"
        categories = {e.category for e in events}
        assert {EventCategory.TROPICAL_CYCLONE, EventCategory.EARTHQUAKE} <= categories
        cyclone = next(e for e in events if e.category is EventCategory.TROPICAL_CYCLONE)
        assert cyclone.id == "gdacs:TC:1001321"
        assert cyclone.severity == pytest.approx(1 / 3)
        assert cyclone.magnitude_unit == "km/h"
        assert cyclone.details["alert_level"] == "green"
        assert cyclone.url is not None
        assert "report.aspx" in cyclone.url

    def test_rejects_non_geojson(self) -> None:
        with pytest.raises(ProviderResponseError):
            GdacsEventFetcher(StubHttp()).transform(since(1), [])


class TestFirms:
    def fetcher(self, http: StubHttp | None = None) -> FirmsFireFetcher:
        return FirmsFireFetcher(
            http or StubHttp(), "SECRET", base_url="https://firms.test/csv", clock=CLOCK
        )

    def test_query_maps_bbox_and_caps_days(self) -> None:
        box = BoundingBox(west=130, south=-13, east=132, north=-12)
        assert self.fetcher().transform_query(
            EventQuery(bbox=box, since=NOW - timedelta(days=9))
        ) == {
            "area": "130.0,-13.0,132.0,-12.0",
            "days": "5",
        }
        assert self.fetcher().transform_query(since(2))["area"] == "world"

    async def test_parses_csv_rows(self) -> None:
        http = StubHttp((FIXTURES / "firms_viirs.csv").read_bytes())
        events = await self.fetcher(http).fetch(since(24))
        assert http.calls[0][0] == "https://firms.test/csv/SECRET/VIIRS_SNPP_NRT/world/1"
        assert len(events) == 3  # the non-numeric row is dropped
        hot = max(events, key=lambda e: e.severity or 0)
        assert hot.category is EventCategory.FIRE_HOTSPOT
        assert hot.severity == 1.0  # 142.9 MW, capped
        assert hot.details["confidence"] == "high"
        assert hot.occurred_at == datetime(2026, 9, 27, 4, 12, tzinfo=UTC)

    def test_error_text_is_a_response_error(self) -> None:
        with pytest.raises(ProviderResponseError, match="Invalid MAP_KEY"):
            self.fetcher().transform(since(1), b"Invalid MAP_KEY.")

    def test_repr_never_contains_the_key(self) -> None:
        assert "SECRET" not in repr(self.fetcher())
