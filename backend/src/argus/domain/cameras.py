"""
Open cameras: public traffic and weather cameras published by road operators.

A camera's facing is shown only when the operator states it, either in a
dedicated field ("S", "West Facing") or as an explicit travel direction in its
title ("US 13 SB"). A camera with no stated facing gets no view cone: guessing
one would draw a direction nobody measured.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, GeoPoint


class CameraNetwork(StrEnum):
    TFL = "tfl"
    FINTRAFFIC = "fintraffic"
    DRIVEBC = "drivebc"
    NSW = "nsw"
    DELDOT = "deldot"


class FeedKind(StrEnum):
    IMAGE = "image"  # a still refreshed by the operator every few minutes
    VIDEO = "video"  # a short recorded clip (TfL)
    HLS = "hls"  # a live stream


class Camera(DomainModel):
    id: str = Field(description="'tfl:00002.00865'")
    network: CameraNetwork
    name: str
    position: GeoPoint
    heading_deg: float | None = Field(
        default=None, ge=0, lt=360, description="Compass facing as stated by the operator"
    )
    feed: FeedKind
    url: str = Field(description="Live stream, clip or still, straight from the operator")
    still_url: str | None = Field(default=None, description="A still for previews, if any")
    description: str | None = None
    source: str


class CameraQuery(DomainModel):
    pass


class NetworkInfo(DomainModel):
    network: CameraNetwork
    operator: str
    region: str
    coverage: BoundingBox = Field(description="Where this network's cameras are")
    license: str


NETWORKS: dict[CameraNetwork, NetworkInfo] = {
    n.network: n
    for n in (
        NetworkInfo(
            network=CameraNetwork.TFL, operator="Transport for London", region="London",
            coverage=BoundingBox(west=-0.6, south=51.25, east=0.35, north=51.72),
            license="Powered by TfL Open Data",
        ),
        NetworkInfo(
            network=CameraNetwork.FINTRAFFIC, operator="Fintraffic", region="Finland",
            coverage=BoundingBox(west=19.0, south=59.6, east=31.6, north=70.1),
            license="Fintraffic / digitraffic.fi, CC BY 4.0",
        ),
        NetworkInfo(
            network=CameraNetwork.DRIVEBC, operator="DriveBC", region="British Columbia",
            coverage=BoundingBox(west=-139.1, south=48.2, east=-114.0, north=60.0),
            license="DriveBC, Government of British Columbia",
        ),
        NetworkInfo(
            network=CameraNetwork.NSW, operator="Transport for NSW", region="New South Wales",
            coverage=BoundingBox(west=141.0, south=-37.6, east=153.7, north=-28.1),
            license="Transport for NSW Open Data, CC BY 4.0",
        ),
        NetworkInfo(
            network=CameraNetwork.DELDOT, operator="DelDOT", region="Delaware",
            coverage=BoundingBox(west=-75.85, south=38.4, east=-75.0, north=39.9),
            license="Delaware Department of Transportation",
        ),
    )
}  # fmt: skip

CAMERAS: dict[CameraNetwork, Capability[CameraQuery, list[Camera]]] = {
    network: Capability(f"cameras.{network.value}", f"Open cameras of {info.operator}.")
    for network, info in NETWORKS.items()
}

_TRAVEL = (
    (r"NORTHBOUND|NB", 0.0), (r"SOUTHBOUND|SB", 180.0),
    (r"EASTBOUND|EB", 90.0), (r"WESTBOUND|WB", 270.0),
)  # fmt: skip
_COMPASS = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}  # fmt: skip
_WORDS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def facing_from_field(value: object) -> float | None:
    """
    A facing from a field that holds one: "S", "N-E", "West Facing (Home)".

    Only the leading compass word counts, so "Home" or "Northern Region"
    give None rather than a guess.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().upper().replace("-", "")
    match = re.match(r"(?:FACING\s+)?(NORTH|SOUTH|EAST|WEST|NE|NW|SE|SW|N|S|E|W)\b", text)
    if not match:
        return None
    token = match.group(1)
    if token in _WORDS:
        rest = text[match.end() :].strip()
        second = re.match(r"(EAST|WEST)\b", rest) if token in ("NORTH", "SOUTH") else None
        token = _WORDS[token] + (_WORDS[second.group(1)] if second else "")
    return _COMPASS[token]


def facing_from_title(title: object) -> float | None:
    """
    A facing from free text, only when it states a travel direction ("US 13 SB").

    Bare compass words are ignored here: in a title they are usually street
    names ("West Dover Connector"), not where the camera looks.
    """
    if not isinstance(title, str):
        return None
    text = title.upper()
    for pattern, heading in _TRAVEL:
        if re.search(rf"\b(?:{pattern})\b", text):
            return heading
    return None
