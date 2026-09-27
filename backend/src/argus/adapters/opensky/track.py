"""
OpenSky ``/tracks/all?icao24=…&time=0`` — the aircraft's current flight.
Marked experimental by OpenSky; used as the fallback track source.

Path rows: ``[time, lat, lon, baro_altitude_m, true_track, on_ground]``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.adapters.adsblol.trace import MAX_POINTS, downsample
from argus.adapters.opensky.auth import OpenSkyAuth
from argus.domain.aviation import AircraftTrack, TrackPoint, TrackQuery
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://opensky-network.org/api"


class OpenSkyTrackFetcher(Fetcher[TrackQuery, AircraftTrack]):
    provider_name = "opensky"

    def __init__(
        self, http: HttpClient, base_url: str = DEFAULT_BASE_URL, auth: OpenSkyAuth | None = None
    ) -> None:
        self._http = http
        self._auth = auth
        self._url = f"{base_url.rstrip('/')}/tracks/all"

    def transform_query(self, query: TrackQuery) -> Mapping[str, str]:
        return {"icao24": query.icao24, "time": "0"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        headers = await self._auth.headers() if self._auth else None
        return await self._http.get_json(
            self._url, provider=self.provider_name, params=params, headers=headers
        )

    def transform(self, query: TrackQuery, raw: Any) -> AircraftTrack:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), list):
            raise ProviderResponseError(self.provider_name, "track has no 'path' list")
        points: list[TrackPoint] = []
        for row in raw["path"]:
            if not isinstance(row, list) or len(row) < 6:
                continue
            when, lat, lon = as_float(row[0]), as_float(row[1]), as_float(row[2])
            if when is None or lat is None or lon is None:
                continue
            track = as_float(row[4])
            try:
                points.append(
                    TrackPoint(
                        at=datetime.fromtimestamp(when, tz=UTC),
                        position=GeoPoint(lat=lat, lon=lon),
                        altitude_m=as_float(row[3]),
                        heading_deg=None if track is None else track % 360,
                        on_ground=bool(row[5]),
                    )
                )
            except ValidationError:
                continue
        callsign = raw.get("callsign")
        return AircraftTrack(
            icao24=query.icao24,
            callsign=callsign.strip() or None if isinstance(callsign, str) else None,
            points=tuple(downsample(points, MAX_POINTS)),
            source=self.provider_name,
        )
