"""
TeleGeography Submarine Cable Map (https://www.submarinecablemap.com).

Licensed CC BY-NC-SA 3.0: attribution is required and commercial use is not
allowed. The attribution travels with the data so the map can display it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.domain.geo import GeoPoint
from argus.domain.infrastructure import Cable, CableNetwork, CableQuery, LandingPoint, LonLat
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://www.submarinecablemap.com/api/v3"
ATTRIBUTION = "Submarine Cable Map © TeleGeography, CC BY-NC-SA 3.0"


def _line(coords: Any) -> tuple[LonLat, ...] | None:
    if not isinstance(coords, list):
        return None
    points: list[LonLat] = []
    for pair in coords:
        if isinstance(pair, list) and len(pair) >= 2:
            lon, lat = as_float(pair[0]), as_float(pair[1])
            if lon is not None and lat is not None:
                points.append((lon, lat))
    return tuple(points) if len(points) >= 2 else None


class TeleGeographyCableFetcher(Fetcher[CableQuery, CableNetwork]):
    provider_name = "telegeography"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def extract(self, params: Mapping[str, str]) -> Any:
        cables, points = await asyncio.gather(
            self._http.get_json(
                f"{self._base_url}/cable/cable-geo.json", provider=self.provider_name, timeout_s=30
            ),
            self._http.get_json(
                f"{self._base_url}/landing-point/landing-point-geo.json",
                provider=self.provider_name,
                timeout_s=30,
            ),
        )
        return {"cables": cables, "landing_points": points}

    def transform(self, query: CableQuery, raw: Any) -> CableNetwork:
        cable_features = (raw.get("cables") or {}).get("features")
        point_features = (raw.get("landing_points") or {}).get("features")
        if not isinstance(cable_features, list) or not isinstance(point_features, list):
            raise ProviderResponseError(self.provider_name, "expected two GeoJSON collections")
        return CableNetwork(
            cables=tuple(c for c in (self._cable(f) for f in cable_features) if c is not None),
            landing_points=tuple(
                p for p in (self._point(f) for f in point_features) if p is not None
            ),
            source=self.provider_name,
            attribution=ATTRIBUTION,
        )

    @staticmethod
    def _cable(feature: Any) -> Cable | None:
        try:
            props, geometry = feature["properties"], feature["geometry"]
            parts = geometry["coordinates"]
            if geometry["type"] == "LineString":
                parts = [parts]
            lines = tuple(line for line in (_line(p) for p in parts) if line is not None)
            if not lines:
                return None
            return Cable(
                id=str(props.get("feature_id") or props["id"]),
                name=props.get("name") or props["id"],
                color=props.get("color"),
                lines=lines,
            )
        except (KeyError, TypeError, ValidationError):
            return None

    @staticmethod
    def _point(feature: Any) -> LandingPoint | None:
        try:
            props = feature["properties"]
            lon, lat = feature["geometry"]["coordinates"][:2]
            return LandingPoint(
                id=props["id"], name=props["name"], position=GeoPoint(lat=lat, lon=lon)
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            return None
