"""
IODA — Internet Outage Detection and Analysis (Georgia Tech), no key.
https://ioda.inetintel.cc.gatech.edu

IODA flags sharp drops in Internet reachability signals (BGP routes, active
probing, Google traffic). A drop can be a government shutdown, a power cut, a
cable cut or a measurement artefact: the event says "signal drop", not why.
Country-level only here, drawn at the country centroid.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, clamp01
from argus.domain.countries import CountryIndex, country_index
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://api.ioda.inetintel.cc.gatech.edu/v2"
SIGNALS = {
    "bgp": "BGP routing",
    "ping-slash24": "active probing",
    "gtr": "Google traffic",
    "merit-nt": "network telescope",
}


class IodaOutageFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "ioda"

    def __init__(
        self,
        http: HttpClient,
        base_url: str = DEFAULT_BASE_URL,
        clock: WallClock | None = None,
        countries: CountryIndex | None = None,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._clock = clock or SystemWallClock()
        self._countries = countries or country_index()

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        return {
            "entityType": "country",
            "from": str(int(query.since.timestamp())),
            "until": str(int(self._clock.utcnow().timestamp())),
            "limit": "500",
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            f"{self._base_url}/outages/events",
            provider=self.provider_name,
            params=params,
            timeout_s=30,
        )

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
            raise ProviderResponseError(self.provider_name, "payload has no 'data' list")
        now = self._clock.utcnow()
        events = (self._parse(e, now) for e in raw["data"])
        return [e for e in events if e is not None]

    def _parse(self, event: Any, now: datetime) -> GeoEvent | None:
        try:
            kind, _, code = str(event["location"]).partition("/")
            country = self._countries.get(code) if kind == "country" else None
            start, duration = as_float(event.get("start")), as_float(event.get("duration"))
            if country is None or start is None:
                return None
            began = datetime.fromtimestamp(start, tz=UTC)
            ended = began + timedelta(seconds=duration or 0)
            score = as_float(event.get("score"))
            ongoing = ended >= now - timedelta(minutes=30)
            return GeoEvent(
                id=f"ioda:{code}:{int(start)}:{event.get('datasource')}",
                category=EventCategory.INTERNET_OUTAGE,
                title=f"Internet signal drop — {country.name}",
                position=country.centroid,
                # The latest moment it is known to be true: "now" while ongoing.
                occurred_at=min(ended, now) if not ongoing else now,
                severity=None if not score or score <= 1 else clamp01(math.log10(score) / 5),
                magnitude=score,
                magnitude_unit="IODA score",
                url=f"https://ioda.inetintel.cc.gatech.edu/country/{code}",
                source=self.provider_name,
                details={
                    "country": country.name,
                    "country_iso2": country.iso2,
                    "signal": SIGNALS.get(str(event.get("datasource")), event.get("datasource")),
                    "started": began.isoformat(),
                    "ongoing": ongoing,
                    "duration_hours": round((duration or 0) / 3600, 1),
                    "cause": "unknown (a signal drop, not necessarily a shutdown)",
                    "placement": "country centroid",
                },
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            return None
