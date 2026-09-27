"""
NASA EONET v3 — curated natural events, no key.
https://eonet.gsfc.nasa.gov/docs/v3

An event carries a track of dated geometries; its position is the latest
one (polygons are reduced to the centroid of their outer ring). Severity is
only derived for storms, from wind speed (150 kt -> 1); other categories have
no comparable magnitude and stay unscored.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, clamp01, parse_utc
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3"

CATEGORY_MAP: dict[str, EventCategory] = {
    "wildfires": EventCategory.WILDFIRE,
    "severeStorms": EventCategory.SEVERE_STORM,
    "volcanoes": EventCategory.VOLCANO,
    "floods": EventCategory.FLOOD,
    "seaLakeIce": EventCategory.SEA_ICE,
    "drought": EventCategory.DROUGHT,
    "dustHaze": EventCategory.DUST_HAZE,
    "landslides": EventCategory.LANDSLIDE,
    "earthquakes": EventCategory.EARTHQUAKE,
    "tempExtremes": EventCategory.EXTREME_TEMPERATURE,
}


def _point(geometry: Mapping[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
        lon, lat = as_float(coords[0]), as_float(coords[1])
        return None if lon is None or lat is None else (lat, lon)
    if geometry.get("type") == "Polygon" and isinstance(coords, list) and coords:
        ring = [(as_float(p[1]), as_float(p[0])) for p in coords[0] if len(p) >= 2]
        valid = [(lat, lon) for lat, lon in ring if lat is not None and lon is not None]
        if valid:
            return (
                sum(lat for lat, _ in valid) / len(valid),
                sum(lon for _, lon in valid) / len(valid),
            )
    return None


class EonetEventFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "eonet"

    def __init__(
        self, http: HttpClient, base_url: str = DEFAULT_BASE_URL, clock: WallClock | None = None
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._clock = clock or SystemWallClock()

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        days = max(1, math.ceil((self._clock.utcnow() - query.since).total_seconds() / 86400))
        params = {"status": "open", "days": str(days), "limit": "500"}
        if query.bbox:
            b = query.bbox
            params["bbox"] = f"{b.west},{b.north},{b.east},{b.south}"  # EONET's order
        return params

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            f"{self._base_url}/events", provider=self.provider_name, params=params
        )

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("events"), list):
            raise ProviderResponseError(self.provider_name, "payload has no 'events' list")
        events = (self._parse(e) for e in raw["events"])
        return [e for e in events if e is not None]

    def _parse(self, event: Any) -> GeoEvent | None:
        try:
            dated: list[tuple[datetime, Mapping[str, Any]]] = []
            for geometry in event.get("geometry") or []:
                when_seen = parse_utc(geometry.get("date"))
                if when_seen is not None:
                    dated.append((when_seen, geometry))
            if not dated:
                return None
            when, latest = max(dated, key=lambda pair: pair[0])
            point = _point(latest)
            if point is None:
                return None
            category_id = (event.get("categories") or [{}])[0].get("id", "")
            category = CATEGORY_MAP.get(category_id, EventCategory.OTHER)
            magnitude = as_float(latest.get("magnitudeValue"))
            unit = latest.get("magnitudeUnit")
            severity = (
                clamp01(magnitude / 150)
                if magnitude is not None
                and category is EventCategory.SEVERE_STORM
                and unit == "kts"
                else None
            )
            sources = event.get("sources") or []
            return GeoEvent(
                id=f"eonet:{event['id']}",
                category=category,
                title=event.get("title") or category.value,
                position=GeoPoint(lat=point[0], lon=point[1]),
                occurred_at=when,
                severity=severity,
                magnitude=magnitude,
                magnitude_unit=unit,
                url=sources[0].get("url") if sources else event.get("link"),
                source=self.provider_name,
                details={
                    "eonet_category": category_id,
                    "track_points": len(dated),
                    "first_seen": min(d for d, _ in dated).isoformat(),
                },
            )
        except (KeyError, TypeError, AttributeError, IndexError, ValidationError):
            return None
