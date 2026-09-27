"""
Parser for the readsb / tar1090 aircraft JSON format.

Used by adsb.lol and every self-hosted ADS-B receiver (readsb, dump1090-fa,
tar1090), so it lives outside any single adapter. The format uses aviation
units; they are converted to SI here, once.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.domain.aviation import Aircraft
from argus.domain.geo import GeoPoint

FEET = 0.3048
KNOT = 1852 / 3600
FEET_PER_MINUTE = FEET / 60


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def parse_aircraft(record: Mapping[str, Any], *, now: datetime, source: str) -> Aircraft | None:
    """One ``ac`` entry -> Aircraft, or None when it has no usable position."""
    lat, lon = _number(record.get("lat")), _number(record.get("lon"))
    if lat is None or lon is None:
        return None

    on_ground = record.get("alt_baro") == "ground"
    altitude_ft = _number(record.get("alt_geom"))
    if altitude_ft is None:
        altitude_ft = _number(record.get("alt_baro"))
    if on_ground:
        altitude_ft = None

    speed_kt = _number(record.get("gs"))
    rate_fpm = _number(record.get("geom_rate"))
    if rate_fpm is None:
        rate_fpm = _number(record.get("baro_rate"))
    track = _number(record.get("track"))
    age_s = _number(record.get("seen_pos")) or _number(record.get("seen")) or 0.0
    hex_id = str(record.get("hex", "")).lower().lstrip("~")  # "~" marks non-ICAO addresses

    try:
        return Aircraft(
            icao24=hex_id,
            callsign=_text(record.get("flight")),
            registration=_text(record.get("r")),
            type_code=_text(record.get("t")),
            squawk=_text(record.get("squawk")),
            origin_country=None,  # not in this format
            position=GeoPoint(lat=lat, lon=lon),
            altitude_m=None if altitude_ft is None else round(altitude_ft * FEET, 1),
            velocity_ms=None if speed_kt is None else round(speed_kt * KNOT, 2),
            heading_deg=None if track is None else track % 360,
            vertical_rate_ms=None if rate_fpm is None else round(rate_fpm * FEET_PER_MINUTE, 2),
            on_ground=on_ground,
            last_contact=now - timedelta(seconds=age_s),
            source=source,
        )
    except ValidationError:
        return None
