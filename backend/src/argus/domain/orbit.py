"""
Orbit propagation: SGP4 in the TEME frame, then Earth-fixed geodetic.

SGP4 (via the ``sgp4`` package, the reference Vallado implementation) returns
positions in TEME. Rotating by Greenwich mean sidereal time gives Earth-fixed
coordinates; polar motion and the equation of the equinoxes are ignored, an
error of well under a kilometre — far below what mean elements guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sgp4.api import WGS72, Satrec

from argus.domain.space import OrbitalElements

WGS84_A_KM = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
_SGP4_EPOCH0 = datetime(1949, 12, 31, tzinfo=UTC)
_J2000_JD = 2451545.0
_UNIX_EPOCH_JD = 2440587.5
# Unit conversions for the mean-motion derivatives, from sgp4/omm.py (SGP4.cpp).
_NDOT_UNITS = 1036800.0 / math.pi
_NDDOT_UNITS = 2985984000.0 / 2.0 / math.pi


@dataclass(frozen=True, slots=True)
class Geodetic:
    lat_deg: float
    lon_deg: float
    alt_km: float


class PropagationError(Exception):
    """SGP4 could not propagate (decayed orbit, invalid elements)."""


def julian_date(at: datetime) -> float:
    return at.timestamp() / 86400.0 + _UNIX_EPOCH_JD


def gmst_radians(at: datetime) -> float:
    """Greenwich mean sidereal time, IAU 1982 model."""
    t = (julian_date(at) - _J2000_JD) / 36525.0
    seconds = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t**2 - 6.2e-6 * t**3
    return math.radians((seconds % 86400.0) / 240.0) % (2 * math.pi)


def teme_to_geodetic(position_km: tuple[float, float, float], at: datetime) -> Geodetic:
    x_t, y_t, z = position_km
    g = gmst_radians(at)
    x = math.cos(g) * x_t + math.sin(g) * y_t
    y = -math.sin(g) * x_t + math.cos(g) * y_t
    return ecef_to_geodetic(x, y, z)


def ecef_to_geodetic(x: float, y: float, z: float) -> Geodetic:
    """WGS84 ellipsoid, iterative (converges to < 1 mm in a few steps)."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    alt = 0.0
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * sin_lat**2)
        alt = p / math.cos(lat) - n if abs(math.cos(lat)) > 1e-12 else abs(z) - n * (1 - WGS84_E2)
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + alt)))
    return Geodetic(math.degrees(lat), math.degrees(lon), alt)


def build_satrec(elements: OrbitalElements) -> Satrec:
    """Initialise SGP4 from OMM mean elements (same conversions as ``sgp4.omm``)."""
    sat = Satrec()
    sat.sgp4init(
        WGS72,
        "i",
        elements.norad_id,
        (elements.epoch - _SGP4_EPOCH0).total_seconds() / 86400.0,
        elements.bstar,
        elements.mean_motion_dot / _NDOT_UNITS,
        elements.mean_motion_ddot / _NDDOT_UNITS,
        elements.eccentricity,
        math.radians(elements.arg_of_pericenter_deg),
        math.radians(elements.inclination_deg),
        math.radians(elements.mean_anomaly_deg),
        elements.mean_motion_rev_per_day / 720.0 * math.pi,  # rev/day -> rad/min
        math.radians(elements.raan_deg),
    )
    return sat


@dataclass(frozen=True, slots=True)
class State:
    geodetic: Geodetic
    speed_kms: float


def propagate(sat: Satrec, at: datetime) -> State:
    jd = julian_date(at)
    whole, fraction = math.floor(jd), jd - math.floor(jd)
    error, position, velocity = sat.sgp4(whole, fraction)
    if error != 0:
        raise PropagationError(f"sgp4 error {error} for {sat.satnum}")
    speed = math.sqrt(sum(v * v for v in velocity))
    return State(teme_to_geodetic(position, at), speed)
