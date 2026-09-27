"""
The Space Devs — Launch Library 2 (https://ll.thespacedevs.com/docs/).

Anonymous access allows 15 requests per hour; an optional token raises it.
One event per launch, placed at its pad, timed at its NET ("no earlier than").
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, parse_utc
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://ll.thespacedevs.com/2.3.0"
PAGE_SIZE = 50


def _name(obj: Any, *path: str) -> str | None:
    for key in path:
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj if isinstance(obj, str) and obj else None


class LaunchLibraryFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "launchlibrary"

    def __init__(
        self, http: HttpClient, token: str | None = None, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        self._http = http
        self._token = token
        self._base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"<LaunchLibraryFetcher authenticated={self._token is not None}>"

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        return {
            "net__gte": query.since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ordering": "net",
            "limit": str(PAGE_SIZE),
            "mode": "normal",
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        headers = {"Authorization": f"Token {self._token}"} if self._token else None
        return await self._http.get_json(
            f"{self._base_url}/launches/",
            provider=self.provider_name,
            params=params,
            headers=headers,
            timeout_s=30.0,
        )

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
            raise ProviderResponseError(self.provider_name, "payload has no 'results' list")
        events = (self._parse(r) for r in raw["results"])
        return [e for e in events if e is not None]

    def _parse(self, launch: Any) -> GeoEvent | None:
        try:
            pad = launch["pad"]
            lat, lon = as_float(pad.get("latitude")), as_float(pad.get("longitude"))
            when = parse_utc(launch.get("net"))
            if lat is None or lon is None or when is None:
                return None
            return GeoEvent(
                id=f"ll2:{launch['id']}",
                category=EventCategory.LAUNCH,
                title=launch.get("name") or "Launch",
                position=GeoPoint(lat=lat, lon=lon),
                occurred_at=when,
                severity=None,
                url=launch.get("url"),
                source=self.provider_name,
                details={
                    "status": _name(launch, "status", "name"),
                    "provider": _name(launch, "launch_service_provider", "name"),
                    "rocket": _name(launch, "rocket", "configuration", "full_name"),
                    "mission": _name(launch, "mission", "name"),
                    "mission_type": _name(launch, "mission", "type"),
                    "orbit": _name(launch, "mission", "orbit", "name"),
                    "pad": pad.get("name"),
                    "site": _name(pad, "location", "name"),
                    "window_start": launch.get("window_start"),
                    "window_end": launch.get("window_end"),
                    "webcast_live": bool(launch.get("webcast_live")),
                },
            )
        except (KeyError, TypeError, AttributeError, ValidationError):
            return None
