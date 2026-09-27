"""
OpenSky Network — ``/api/states/all``.

State vectors arrive as positional arrays. Indices are named once in
:class:`_Col` (per https://openskynetwork.github.io/opensky-api/rest.html);
reading them by bare number is how OSINT-War-Room ended up treating the
barometric altitude as the ``on_ground`` flag.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

from pydantic import ValidationError

from argus.adapters.opensky.auth import OpenSkyAuth
from argus.domain.aviation import Aircraft, AircraftQuery
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://opensky-network.org/api"


class _Col(IntEnum):
    ICAO24 = 0
    CALLSIGN = 1
    ORIGIN_COUNTRY = 2
    TIME_POSITION = 3
    LAST_CONTACT = 4
    LONGITUDE = 5
    LATITUDE = 6
    BARO_ALTITUDE = 7
    ON_GROUND = 8
    VELOCITY = 9
    TRUE_TRACK = 10
    VERTICAL_RATE = 11
    SENSORS = 12
    GEO_ALTITUDE = 13
    SQUAWK = 14
    SPI = 15
    POSITION_SOURCE = 16


_MIN_COLUMNS = _Col.GEO_ALTITUDE + 1


class OpenSkyAircraftFetcher(Fetcher[AircraftQuery, list[Aircraft]]):
    provider_name = "opensky"

    def __init__(
        self, http: HttpClient, base_url: str = DEFAULT_BASE_URL, auth: OpenSkyAuth | None = None
    ) -> None:
        self._http = http
        self._auth = auth
        self._url = f"{base_url.rstrip('/')}/states/all"

    def transform_query(self, query: AircraftQuery) -> Mapping[str, str]:
        if query.bbox is None:
            return {}
        box = query.bbox
        return {
            "lamin": str(box.south),
            "lomin": str(box.west),
            "lamax": str(box.north),
            "lomax": str(box.east),
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        headers = await self._auth.headers() if self._auth else None
        return await self._http.get_json(
            self._url, provider=self.provider_name, params=params, headers=headers
        )

    def transform(self, query: AircraftQuery, raw: Any) -> list[Aircraft]:
        if not isinstance(raw, dict) or "states" not in raw:
            raise ProviderResponseError(self.provider_name, "payload has no 'states' field")
        rows = raw["states"] or []  # OpenSky sends null for an empty sky
        if not isinstance(rows, list):
            raise ProviderResponseError(self.provider_name, "'states' is not a list")

        aircraft: list[Aircraft] = []
        skipped = 0
        for row in rows:
            parsed = self._parse_row(row)
            if parsed is None:
                skipped += 1
            else:
                aircraft.append(parsed)
        if skipped:
            logger.debug("opensky: skipped %d unusable rows", skipped)
        return aircraft

    def _parse_row(self, row: Any) -> Aircraft | None:
        if not isinstance(row, list) or len(row) < _MIN_COLUMNS:
            return None
        lat, lon = row[_Col.LATITUDE], row[_Col.LONGITUDE]
        if lat is None or lon is None:
            return None
        callsign = (row[_Col.CALLSIGN] or "").strip() or None
        altitude = row[_Col.GEO_ALTITUDE]
        if altitude is None:
            altitude = row[_Col.BARO_ALTITUDE]
        try:
            return Aircraft(
                icao24=str(row[_Col.ICAO24]).lower(),
                callsign=callsign,
                origin_country=row[_Col.ORIGIN_COUNTRY] or None,
                position=GeoPoint(lat=lat, lon=lon),
                altitude_m=altitude,
                velocity_ms=row[_Col.VELOCITY],
                heading_deg=_normalise_heading(row[_Col.TRUE_TRACK]),
                vertical_rate_ms=row[_Col.VERTICAL_RATE],
                on_ground=bool(row[_Col.ON_GROUND]),
                last_contact=datetime.fromtimestamp(row[_Col.LAST_CONTACT], tz=UTC),
                source=self.provider_name,
            )
        except (ValidationError, TypeError, ValueError, OverflowError, OSError):
            return None


def _normalise_heading(value: float | None) -> float | None:
    return None if value is None else float(value) % 360
