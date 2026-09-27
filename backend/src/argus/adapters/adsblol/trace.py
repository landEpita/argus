"""
adsb.lol trace files: today's positions for one aircraft (tar1090 format).
``/data/traces/{last two hex digits}/trace_full_{hex}.json``

Rows are ``[seconds since timestamp, lat, lon, altitude_ft|"ground"|null,
ground_speed_kt, track_deg, flags, vertical_rate_fpm, …]``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.adapters.readsb import FEET, KNOT
from argus.domain.aviation import AircraftTrack, TrackPoint, TrackQuery
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://adsb.lol/data/traces"
MAX_POINTS = 2_000


def downsample[T](items: list[T], limit: int) -> list[T]:
    """Evenly thin a sequence to at most ``limit`` items, always keeping the last one."""
    if len(items) <= limit:
        return items
    step = len(items) / (limit - 1)
    picked = [items[int(i * step)] for i in range(limit - 1)]
    return [*picked, items[-1]]


class AdsbLolTraceFetcher(Fetcher[TrackQuery, AircraftTrack]):
    provider_name = "adsblol"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def transform_query(self, query: TrackQuery) -> Mapping[str, str]:
        return {"hex": query.icao24}

    async def extract(self, params: Mapping[str, str]) -> Any:
        hex_id = params["hex"]
        url = f"{self._base_url}/{hex_id[-2:]}/trace_full_{hex_id}.json"
        return await self._http.get_json(url, provider=self.provider_name)

    def transform(self, query: TrackQuery, raw: Any) -> AircraftTrack:
        if not isinstance(raw, dict) or not isinstance(raw.get("trace"), list):
            raise ProviderResponseError(self.provider_name, "trace file has no 'trace' list")
        base = as_float(raw.get("timestamp"))
        if base is None:
            raise ProviderResponseError(self.provider_name, "trace file has no timestamp")
        start = datetime.fromtimestamp(base, tz=UTC)
        points = [p for p in (self._point(row, start) for row in raw["trace"]) if p is not None]
        callsign = next(
            (
                str(row[8]["flight"]).strip() or None
                for row in reversed(raw["trace"])
                if isinstance(row, list)
                and len(row) > 8
                and isinstance(row[8], dict)
                and row[8].get("flight")
            ),
            None,
        )
        return AircraftTrack(
            icao24=query.icao24,
            callsign=callsign,
            points=tuple(downsample(points, MAX_POINTS)),
            source=self.provider_name,
        )

    @staticmethod
    def _point(row: Any, start: datetime) -> TrackPoint | None:
        if not isinstance(row, list) or len(row) < 6:
            return None
        offset, lat, lon = as_float(row[0]), as_float(row[1]), as_float(row[2])
        if offset is None or lat is None or lon is None:
            return None
        on_ground = row[3] == "ground"
        altitude_ft = None if on_ground else as_float(row[3])
        speed_kt, track = as_float(row[4]), as_float(row[5])
        try:
            return TrackPoint(
                at=start + timedelta(seconds=offset),
                position=GeoPoint(lat=lat, lon=lon),
                altitude_m=None if altitude_ft is None else round(altitude_ft * FEET, 1),
                velocity_ms=None if speed_kt is None else round(speed_kt * KNOT, 2),
                heading_deg=None if track is None else track % 360,
                on_ground=on_ground,
            )
        except ValidationError:
            return None
