"""
NASA FIRMS — active fire / thermal anomaly detections. Needs a free MAP_KEY:
https://firms.modaps.eosdis.nasa.gov/api/map_key/

Each row is one satellite pixel flagged as hot, not a confirmed wildfire;
the category says so (``fire_hotspot``). Severity comes from fire radiative
power: 100 MW or more -> 1.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, clamp01
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_SOURCE = "VIIRS_SNPP_NRT"
MAX_DAYS = 5
CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


class FirmsFireFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "firms"

    def __init__(
        self,
        http: HttpClient,
        map_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        satellite_source: str = DEFAULT_SOURCE,
        clock: WallClock | None = None,
    ) -> None:
        self._http = http
        self._key = map_key
        self._base_url = base_url.rstrip("/")
        self._source = satellite_source
        self._clock = clock or SystemWallClock()

    def __repr__(self) -> str:  # never leak the key into logs
        return f"<FirmsFireFetcher source={self._source}>"

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        seconds = (self._clock.utcnow() - query.since).total_seconds()
        days = min(MAX_DAYS, max(1, math.ceil(seconds / 86400)))
        b = query.bbox
        area = "world" if b is None else f"{b.west},{b.south},{b.east},{b.north}"
        return {"area": area, "days": str(days)}

    async def extract(self, params: Mapping[str, str]) -> Any:
        url = f"{self._base_url}/{self._key}/{self._source}/{params['area']}/{params['days']}"
        return await self._http.get_bytes(url, provider=self.provider_name)

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if not text.startswith("latitude,"):
            # FIRMS answers errors ("Invalid MAP_KEY.") as 200/400 plain text.
            raise ProviderResponseError(self.provider_name, f"unexpected body: {text[:80]!r}")
        rows = csv.DictReader(io.StringIO(text))
        events = (self._parse(r) for r in rows)
        return [e for e in events if e is not None]

    def _parse(self, row: Mapping[str, str]) -> GeoEvent | None:
        lat, lon = as_float(row.get("latitude")), as_float(row.get("longitude"))
        if lat is None or lon is None:
            return None
        try:
            hhmm = row["acq_time"].zfill(4)
            when = datetime.strptime(f"{row['acq_date']} {hhmm}", "%Y-%m-%d %H%M").replace(
                tzinfo=UTC
            )
            frp = as_float(row.get("frp"))
            satellite = row.get("satellite", "")
            return GeoEvent(
                id=f"firms:{satellite}:{row['acq_date']}T{hhmm}:{lat:.4f},{lon:.4f}",
                category=EventCategory.FIRE_HOTSPOT,
                title=f"Thermal anomaly ({row.get('instrument', 'satellite')})",
                position=GeoPoint(lat=lat, lon=lon),
                occurred_at=when,
                severity=None if frp is None else clamp01(frp / 100),
                magnitude=frp,
                magnitude_unit="MW",
                url=None,
                source=self.provider_name,
                details={
                    "confidence": CONFIDENCE.get(row.get("confidence", ""), row.get("confidence")),
                    "satellite": satellite or None,
                    "day_night": row.get("daynight") or None,
                    "brightness_k": as_float(row.get("bright_ti4")),
                },
            )
        except (KeyError, ValueError, ValidationError):
            return None
