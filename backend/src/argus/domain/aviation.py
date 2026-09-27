"""Aviation domain: aircraft states and the capability that serves them."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, GeoPoint


class Aircraft(DomainModel):
    """
    One aircraft state vector, normalised across providers.

    Units are SI throughout (metres, metres per second). Conversion to feet or
    knots is a presentation concern and belongs to the client.
    """

    icao24: str = Field(min_length=6, max_length=6, description="ICAO 24-bit address, hex")
    callsign: str | None = None
    registration: str | None = None
    type_code: str | None = Field(default=None, description="ICAO aircraft type designator")
    squawk: str | None = None
    origin_country: str | None = None
    position: GeoPoint
    altitude_m: float | None = Field(default=None, description="Geometric, else barometric")
    velocity_ms: float | None = Field(default=None, ge=0)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    vertical_rate_ms: float | None = None
    on_ground: bool = False
    last_contact: datetime
    source: str = Field(description="Provider that produced this state")


class AircraftQuery(DomainModel):
    bbox: BoundingBox | None = None
    include_on_ground: bool = False


AIRCRAFT_STATES: Capability[AircraftQuery, list[Aircraft]] = Capability(
    "aviation.aircraft_states",
    "Live aircraft state vectors, optionally limited to a bounding box.",
)

MILITARY_AIRCRAFT: Capability[AircraftQuery, list[Aircraft]] = Capability(
    "aviation.military_aircraft",
    "Aircraft flagged as military by the provider's database, worldwide.",
)


class TrackPoint(DomainModel):
    at: datetime
    position: GeoPoint
    altitude_m: float | None = None
    velocity_ms: float | None = None
    heading_deg: float | None = None
    on_ground: bool = False


class AircraftTrack(DomainModel):
    icao24: str
    callsign: str | None = None
    points: tuple[TrackPoint, ...]
    source: str


class TrackQuery(DomainModel):
    icao24: str = Field(pattern=r"^[0-9a-f]{6}$")


AIRCRAFT_TRACK: Capability[TrackQuery, AircraftTrack] = Capability(
    "aviation.aircraft_track", "Recent positions of one aircraft (today's flight)."
)
