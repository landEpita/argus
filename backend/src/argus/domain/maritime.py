"""Vessels from AIS position reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, GeoPoint


class ShipCategory(StrEnum):
    CARGO = "cargo"
    TANKER = "tanker"
    PASSENGER = "passenger"
    FISHING = "fishing"
    MILITARY = "military"
    LAW_ENFORCEMENT = "law_enforcement"
    TUG = "tug"
    HIGH_SPEED = "high_speed"
    PLEASURE = "pleasure"
    OTHER = "other"
    UNKNOWN = "unknown"


def ship_category(type_code: int | None) -> ShipCategory:
    """ITU-R M.1371 ship-and-cargo type code -> category."""
    if type_code is None or type_code <= 0:
        return ShipCategory.UNKNOWN
    if type_code == 30:
        return ShipCategory.FISHING
    if type_code in (31, 32, 52):
        return ShipCategory.TUG
    if type_code == 35:
        return ShipCategory.MILITARY
    if type_code == 55:
        return ShipCategory.LAW_ENFORCEMENT
    if type_code in (36, 37):
        return ShipCategory.PLEASURE
    decade = type_code // 10
    return {
        4: ShipCategory.HIGH_SPEED,
        6: ShipCategory.PASSENGER,
        7: ShipCategory.CARGO,
        8: ShipCategory.TANKER,
    }.get(decade, ShipCategory.OTHER)


class Vessel(DomainModel):
    mmsi: str = Field(pattern=r"^\d{9}$")
    name: str | None = None
    call_sign: str | None = None
    imo: str | None = None
    ship_type: int | None = Field(default=None, description="ITU-R M.1371 type code")
    category: ShipCategory = ShipCategory.UNKNOWN
    position: GeoPoint
    speed_ms: float | None = Field(default=None, ge=0)
    course_deg: float | None = Field(default=None, ge=0, lt=360)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    destination: str | None = None
    last_seen: datetime
    source: str


class VesselQuery(DomainModel):
    bbox: BoundingBox | None = None


VESSEL_POSITIONS: Capability[VesselQuery, list[Vessel]] = Capability(
    "maritime.vessel_positions", "Latest known position of each vessel heard recently."
)
