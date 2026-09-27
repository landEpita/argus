"""
Pure parsing of aisstream.io messages (https://aisstream.io/documentation).

Position reports and static data arrive as separate messages, so parsing
yields partial updates that the store merges per MMSI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from argus.adapters._util import as_float, parse_utc

KNOT = 1852 / 3600
_POSITION_TYPES = ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport")
_COURSE_UNAVAILABLE = 360
_SPEED_UNAVAILABLE = 102.3


@dataclass(frozen=True, slots=True)
class PositionUpdate:
    mmsi: str
    lat: float
    lon: float
    speed_ms: float | None
    course_deg: float | None
    heading_deg: float | None
    name: str | None
    at: datetime


@dataclass(frozen=True, slots=True)
class StaticUpdate:
    mmsi: str
    name: str | None
    call_sign: str | None
    imo: str | None
    ship_type: int | None
    destination: str | None


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace("@", " ").strip()  # AIS pads text fields with '@'
    return cleaned or None


def _parse_time(meta: dict[str, Any], fallback: datetime) -> datetime:
    raw = meta.get("time_utc")
    if isinstance(raw, str):
        # "2026-09-27 16:01:02.123456789 +0000 UTC" (Go format): keep date, time, micros.
        head = raw.split(" +")[0]
        if "." in head:
            base, fraction = head.split(".", 1)
            head = f"{base}.{fraction[:6]}"
        parsed = parse_utc(head.replace(" ", "T"))
        if parsed is not None:
            return parsed
    return fallback


def parse_message(message: Any, *, now: datetime) -> PositionUpdate | StaticUpdate | None:
    if not isinstance(message, dict):
        return None
    kind = message.get("MessageType")
    meta = message.get("MetaData") or {}
    body = (message.get("Message") or {}).get(kind) or {}
    mmsi = str(meta.get("MMSI") or body.get("UserID") or "")
    if len(mmsi) != 9 or not mmsi.isdigit():
        return None

    if kind in _POSITION_TYPES:
        lat = as_float(body.get("Latitude", meta.get("latitude")))
        lon = as_float(body.get("Longitude", meta.get("longitude")))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None  # 91/181 mean "not available" in AIS
        sog = as_float(body.get("Sog"))
        cog = as_float(body.get("Cog"))
        heading = as_float(body.get("TrueHeading"))
        return PositionUpdate(
            mmsi=mmsi,
            lat=lat,
            lon=lon,
            speed_ms=None if sog is None or sog >= _SPEED_UNAVAILABLE else round(sog * KNOT, 2),
            course_deg=None if cog is None or cog >= _COURSE_UNAVAILABLE else cog,
            heading_deg=None if heading is None or heading >= 360 else heading,
            name=_clean(meta.get("ShipName")),
            at=_parse_time(meta, now),
        )

    if kind == "ShipStaticData":
        imo = body.get("ImoNumber")
        ship_type = body.get("Type")
        return StaticUpdate(
            mmsi=mmsi,
            name=_clean(body.get("Name")) or _clean(meta.get("ShipName")),
            call_sign=_clean(body.get("CallSign")),
            imo=str(imo) if isinstance(imo, int) and imo > 0 else None,
            ship_type=ship_type if isinstance(ship_type, int) and ship_type > 0 else None,
            destination=_clean(body.get("Destination")),
        )
    return None
