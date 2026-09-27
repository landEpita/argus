"""
USGS Earthquake Hazards Program — GeoJSON summary feeds, no key.
https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php

Severity: magnitude mapped linearly, M2 -> 0, M8 -> 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, clamp01
from argus.domain.countries import country_index
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"

# Smallest feed covering the window. Longer windows raise the magnitude floor
# because the "all" feeds for a week or a month run to tens of thousands of events.
_FEEDS: tuple[tuple[timedelta, str], ...] = (
    (timedelta(hours=1), "all_hour"),
    (timedelta(days=1), "all_day"),
    (timedelta(days=7), "2.5_week"),
    (timedelta(days=30), "4.5_month"),
)


class UsgsEarthquakeFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "usgs"

    def __init__(
        self, http: HttpClient, base_url: str = DEFAULT_BASE_URL, clock: WallClock | None = None
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._clock = clock or SystemWallClock()

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        window = self._clock.utcnow() - query.since
        name = next((feed for span, feed in _FEEDS if window <= span), _FEEDS[-1][1])
        return {"feed": name}

    async def extract(self, params: Mapping[str, str]) -> Any:
        url = f"{self._base_url}/{params['feed']}.geojson"
        return await self._http.get_json(url, provider=self.provider_name)

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("features"), list):
            raise ProviderResponseError(self.provider_name, "not a GeoJSON FeatureCollection")
        events = (self._parse(f) for f in raw["features"])
        return [e for e in events if e is not None]

    def _parse(self, feature: Any) -> GeoEvent | None:
        try:
            props = feature["properties"]
            lon, lat, depth = (feature["geometry"]["coordinates"] + [None])[:3]
            magnitude = as_float(props.get("mag"))
            tsunami = props.get("tsunami") == 1
            return GeoEvent(
                id=f"usgs:{feature['id']}",
                category=EventCategory.EARTHQUAKE,
                title=props.get("title") or props.get("place") or "Earthquake",
                position=GeoPoint(lat=lat, lon=lon),
                occurred_at=datetime.fromtimestamp(props["time"] / 1000, tz=UTC),
                severity=None if magnitude is None else clamp01((magnitude - 2) / 6),
                magnitude=magnitude,
                magnitude_unit=props.get("magType"),
                url=props.get("url"),
                source=self.provider_name,
                details={
                    "place": props.get("place"),
                    "country_iso2": country_index().country_of_place(props.get("place")),
                    "depth_km": as_float(depth),
                    "tsunami_warning": tsunami,
                    "pager_alert": props.get("alert"),
                    "felt_reports": props.get("felt"),
                    "review_status": props.get("status"),
                },
            )
        except (KeyError, TypeError, IndexError, ValidationError, OverflowError, OSError):
            return None
