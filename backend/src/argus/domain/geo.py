"""Geospatial value objects shared by every domain."""

from __future__ import annotations

import math
from typing import Self

from pydantic import Field, model_validator

from argus.domain.base import DomainModel

Latitude = float
Longitude = float


class GeoPoint(DomainModel):
    """A WGS84 position."""

    lat: Latitude = Field(ge=-90, le=90)
    lon: Longitude = Field(ge=-180, le=180)


class BoundingBox(DomainModel):
    """
    An axis-aligned WGS84 box.

    Boxes crossing the antimeridian are not supported yet: callers must split
    them in two. Rejecting them here is safer than silently returning the
    complement of what the user is looking at.
    """

    west: Longitude = Field(ge=-180, le=180)
    south: Latitude = Field(ge=-90, le=90)
    east: Longitude = Field(ge=-180, le=180)
    north: Latitude = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.south > self.north:
            raise ValueError("south must be <= north")
        if self.west > self.east:
            raise ValueError("west must be <= east (antimeridian boxes are not supported)")
        return self

    @classmethod
    def parse(cls, raw: str) -> BoundingBox:
        """Parse the conventional ``west,south,east,north`` string."""
        parts = raw.split(",")
        if len(parts) != 4:
            raise ValueError("bbox must be 'west,south,east,north'")
        try:
            west, south, east, north = (float(p) for p in parts)
        except ValueError as exc:
            raise ValueError("bbox values must be numbers") from exc
        return cls(west=west, south=south, east=east, north=north)

    def contains(self, point: GeoPoint) -> bool:
        return self.south <= point.lat <= self.north and self.west <= point.lon <= self.east

    def cache_key(self, precision: int = 1) -> str:
        """
        A key that is stable across tiny viewport moves.

        Rounding outwards keeps the cached box a superset of the requested one,
        so a cache hit never drops objects at the edges.
        """
        factor = float(10**precision)

        def down(v: float) -> float:
            return math.floor(v * factor) / factor

        def up(v: float) -> float:
            return math.ceil(v * factor) / factor

        return f"{down(self.west)},{down(self.south)},{up(self.east)},{up(self.north)}"

    def expanded_to_grid(self, precision: int = 1) -> BoundingBox:
        """The box matching :meth:`cache_key`, clamped to valid coordinates."""
        west, south, east, north = (float(v) for v in self.cache_key(precision).split(","))
        return BoundingBox(
            west=max(west, -180), south=max(south, -90), east=min(east, 180), north=min(north, 90)
        )
