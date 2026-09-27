"""
OpenStreetMap via the Overpass API. No key; public instances ask for modest use,
so queries are limited to small boxes and cached for a day.

What OSM holds is what volunteers mapped: coverage is uneven, and military
sites in particular are often missing or deliberately vague.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.domain.geo import GeoPoint
from argus.domain.infrastructure import Facility, FacilityKind, FacilityQuery
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError, UnsupportedQueryError

MAX_AREA_SQ_DEG = 25.0  # one 5° x 5° tile; the service splits larger views into tiles
TIMEOUT_S = 80  # public instances are slow under load (30-40 s observed for a tile)
MAX_RESULTS = 2_000

# Tag filters per kind, in Overpass QL.
FILTERS: dict[FacilityKind, tuple[str, ...]] = {
    FacilityKind.MILITARY: ('["military"~"^(base|airfield|naval_base)$"]',),
    FacilityKind.DATA_CENTER: ('["telecom"="data_center"]',),
    FacilityKind.NUCLEAR_PLANT: (
        '["plant:source"="nuclear"]',
        '["generator:source"="nuclear"]["power"="plant"]',
    ),
}

MIRRORS = {
    "overpass-de": "https://overpass-api.de/api/interpreter",
    "overpass-kumi": "https://overpass.kumi.systems/api/interpreter",
    "overpass-coffee": "https://overpass.private.coffee/api/interpreter",
}


def build_query(query: FacilityQuery) -> str:
    b = query.bbox
    area = f"({b.south},{b.west},{b.north},{b.east})"
    selectors = "".join(f"nwr{f}{area};" for f in FILTERS[query.kind])
    return f"[out:json][timeout:{TIMEOUT_S}];({selectors});out center tags {MAX_RESULTS};"


class OverpassFacilityFetcher(Fetcher[FacilityQuery, list[Facility]]):
    def __init__(self, http: HttpClient, url: str, provider_name: str) -> None:
        self._http = http
        self._url = url
        self.provider_name = provider_name

    def transform_query(self, query: FacilityQuery) -> Mapping[str, str]:
        b = query.bbox
        area = (b.east - b.west) * (b.north - b.south)
        if area > MAX_AREA_SQ_DEG:
            raise UnsupportedQueryError(
                self.provider_name, f"box is {area:.0f} sq deg (max {MAX_AREA_SQ_DEG:.0f})"
            )
        return {"data": build_query(query)}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            self._url, provider=self.provider_name, params=params, timeout_s=TIMEOUT_S + 5
        )

    def transform(self, query: FacilityQuery, raw: Any) -> list[Facility]:
        if not isinstance(raw, dict) or not isinstance(raw.get("elements"), list):
            raise ProviderResponseError(self.provider_name, "payload has no 'elements' list")
        facilities = (self._parse(query.kind, e) for e in raw["elements"])
        return [f for f in facilities if f is not None]

    def _parse(self, kind: FacilityKind, element: Any) -> Facility | None:
        if not isinstance(element, dict):
            return None
        center = element.get("center") or element
        lat, lon = as_float(center.get("lat")), as_float(center.get("lon"))
        if lat is None or lon is None:
            return None
        tags = element.get("tags") or {}
        osm_type, osm_id = element.get("type"), element.get("id")
        try:
            return Facility(
                id=f"osm:{osm_type}/{osm_id}",
                kind=kind,
                name=tags.get("name:en") or tags.get("name"),
                position=GeoPoint(lat=lat, lon=lon),
                operator=tags.get("operator"),
                subtype=tags.get("military") or tags.get("plant:output:electricity"),
                url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                source=self.provider_name,
            )
        except ValidationError:
            return None
