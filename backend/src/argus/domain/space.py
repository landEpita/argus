"""Satellites: orbital elements (input) and propagated positions (output)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import GeoPoint


class SatelliteGroup(StrEnum):
    """CelesTrak group names; each is one layer on the map."""

    STATIONS = "stations"
    VISUAL = "visual"
    GPS = "gps-ops"
    GALILEO = "galileo"
    WEATHER = "weather"
    MILITARY = "military"
    STARLINK = "starlink"


class OrbitalElements(DomainModel):
    """A CCSDS OMM mean-element set, as published by CelesTrak (SGP4 inputs)."""

    norad_id: int = Field(gt=0)
    name: str
    international_designator: str | None = None
    epoch: AwareDatetime
    mean_motion_rev_per_day: float = Field(gt=0)
    eccentricity: float = Field(ge=0, lt=1)
    inclination_deg: float
    raan_deg: float
    arg_of_pericenter_deg: float
    mean_anomaly_deg: float
    bstar: float
    mean_motion_dot: float
    mean_motion_ddot: float


class ElementsQuery(DomainModel):
    group: SatelliteGroup


class SatellitePosition(DomainModel):
    norad_id: int
    name: str
    group: SatelliteGroup
    position: GeoPoint
    altitude_km: float
    speed_kms: float = Field(description="Inertial speed")
    at: datetime
    elements_age_days: float = Field(description="Accuracy degrades as elements age")


ORBITAL_ELEMENTS: Capability[ElementsQuery, list[OrbitalElements]] = Capability(
    "space.orbital_elements", "Mean orbital elements (OMM) for a satellite group."
)
