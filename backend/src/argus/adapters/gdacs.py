"""
GDACS — Global Disaster Alert and Coordination System (UN / EC JRC), no key.
https://www.gdacs.org

Severity is GDACS's own alert level: Green 1/3, Orange 2/3, Red 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, parse_utc
from argus.domain.countries import country_index
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://www.gdacs.org/gdacsapi/api"

EVENT_TYPES: dict[str, EventCategory] = {
    "EQ": EventCategory.EARTHQUAKE,
    "TC": EventCategory.TROPICAL_CYCLONE,
    "FL": EventCategory.FLOOD,
    "VO": EventCategory.VOLCANO,
    "DR": EventCategory.DROUGHT,
    "WF": EventCategory.WILDFIRE,
    "TS": EventCategory.TSUNAMI,
}
ALERT_SEVERITY = {"green": 1 / 3, "orange": 2 / 3, "red": 1.0}


class GdacsEventFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "gdacs"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        return {
            "eventlist": ";".join(EVENT_TYPES),
            "alertlevel": "Green;Orange;Red",
            "fromdate": query.since.date().isoformat(),
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            f"{self._base_url}/events/geteventlist/SEARCH",
            provider=self.provider_name,
            params=params,
        )

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("features"), list):
            raise ProviderResponseError(self.provider_name, "not a GeoJSON FeatureCollection")
        events = (self._parse(f) for f in raw["features"])
        return [e for e in events if e is not None]

    def _parse(self, feature: Any) -> GeoEvent | None:
        try:
            props = feature["properties"]
            lon, lat = feature["geometry"]["coordinates"][:2]
            event_type = props["eventtype"]
            alert = str(props.get("alertlevel") or "").lower()
            when = parse_utc(props.get("todate")) or parse_utc(props.get("fromdate"))
            if when is None:
                return None
            severity_data = props.get("severitydata") or {}
            return GeoEvent(
                id=f"gdacs:{event_type}:{props['eventid']}",
                category=EVENT_TYPES.get(event_type, EventCategory.OTHER),
                title=props.get("name") or event_type,
                position=GeoPoint(lat=lat, lon=lon),
                occurred_at=when,
                severity=ALERT_SEVERITY.get(alert),
                magnitude=as_float(severity_data.get("severity")),
                magnitude_unit=severity_data.get("severityunit") or None,
                url=(props.get("url") or {}).get("report"),
                source=self.provider_name,
                details={
                    "alert_level": alert or None,
                    "country": props.get("country") or None,
                    # GDACS lists affected countries "A, B"; the first is the main one.
                    "country_iso2": next(
                        iter(country_index().mentions(str(props.get("country") or ""))), None
                    ),
                    "severity_text": severity_data.get("severitytext"),
                    "started": props.get("fromdate"),
                    "current": props.get("iscurrent") == "true",
                },
            )
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            return None
