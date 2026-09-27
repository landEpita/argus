"""Fixed infrastructure: facilities (points) and submarine cables (lines)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, GeoPoint

LonLat = tuple[float, float]


class FacilityKind(StrEnum):
    MILITARY = "military"
    DATA_CENTER = "data-center"
    NUCLEAR_PLANT = "nuclear-plant"


class Facility(DomainModel):
    id: str = Field(description="'osm:node/123'")
    kind: FacilityKind
    name: str | None = None
    position: GeoPoint
    operator: str | None = None
    subtype: str | None = Field(default=None, description="e.g. airfield, naval_base")
    url: str | None = None
    source: str


class FacilityQuery(DomainModel):
    kind: FacilityKind
    bbox: BoundingBox


class Cable(DomainModel):
    id: str
    name: str
    color: str | None = None
    lines: tuple[tuple[LonLat, ...], ...] = Field(description="MultiLineString, lon/lat pairs")


class LandingPoint(DomainModel):
    id: str
    name: str
    position: GeoPoint


class CableNetwork(DomainModel):
    cables: tuple[Cable, ...]
    landing_points: tuple[LandingPoint, ...]
    source: str
    attribution: str


class CableQuery(DomainModel):
    pass


FACILITIES: Capability[FacilityQuery, list[Facility]] = Capability(
    "infrastructure.facilities", "Mapped facilities of one kind within a box."
)
SUBMARINE_CABLES: Capability[CableQuery, CableNetwork] = Capability(
    "infrastructure.submarine_cables", "Submarine cable routes and landing points."
)
