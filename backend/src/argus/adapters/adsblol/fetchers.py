"""
adsb.lol — community ADS-B aggregator, no key required (https://api.adsb.lol).

Two capabilities:
- aircraft in a box (fallback for OpenSky), via ``/v2/point/{lat}/{lon}/{nm}``,
  which is limited to a 250 NM radius;
- military aircraft worldwide, via ``/v2/mil``.
"""

from __future__ import annotations

import math
from abc import abstractmethod
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from argus.adapters.readsb import parse_aircraft
from argus.domain.aviation import Aircraft, AircraftQuery
from argus.domain.geo import BoundingBox
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError, UnsupportedQueryError

DEFAULT_BASE_URL = "https://api.adsb.lol"
MAX_RADIUS_NM = 250
EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def covering_circle(box: BoundingBox) -> tuple[float, float, float]:
    """Centre and radius (NM) of a circle containing the whole box."""
    lat, lon = (box.south + box.north) / 2, (box.west + box.east) / 2
    radius = max(
        haversine_nm(lat, lon, corner_lat, corner_lon)
        for corner_lat in (box.south, box.north)
        for corner_lon in (box.west, box.east)
    )
    return lat, lon, radius


class _AdsbLolFetcher(Fetcher[AircraftQuery, list[Aircraft]]):
    provider_name = "adsblol"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    @abstractmethod
    def _url(self, params: Mapping[str, str]) -> str: ...

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url(params), provider=self.provider_name)

    def transform(self, query: AircraftQuery, raw: Any) -> list[Aircraft]:
        if not isinstance(raw, dict) or not isinstance(raw.get("ac"), list):
            raise ProviderResponseError(self.provider_name, "payload has no 'ac' list")
        now_ms = raw.get("now")
        now = (
            datetime.fromtimestamp(now_ms / 1000, tz=UTC)
            if isinstance(now_ms, int | float)
            else datetime.now(UTC)
        )
        parsed = (parse_aircraft(r, now=now, source=self.provider_name) for r in raw["ac"])
        return [a for a in parsed if a is not None]


class AdsbLolAircraftFetcher(_AdsbLolFetcher):
    def transform_query(self, query: AircraftQuery) -> Mapping[str, str]:
        if query.bbox is None:
            raise UnsupportedQueryError(self.provider_name, "needs a bounding box")
        lat, lon, radius = covering_circle(query.bbox)
        if radius > MAX_RADIUS_NM:
            raise UnsupportedQueryError(
                self.provider_name, f"box needs a {radius:.0f} NM radius (max {MAX_RADIUS_NM})"
            )
        return {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "radius": str(max(1, math.ceil(radius)))}

    def _url(self, params: Mapping[str, str]) -> str:
        return f"{self._base_url}/v2/point/{params['lat']}/{params['lon']}/{params['radius']}"


class AdsbLolMilitaryFetcher(_AdsbLolFetcher):
    def _url(self, params: Mapping[str, str]) -> str:
        return f"{self._base_url}/v2/mil"
