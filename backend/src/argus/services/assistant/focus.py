"""
Where the map should go after an answer, from the tools that were called.

Never from the model's words: a focus is only proposed when a tool actually
read data about a place, and only map layers that show that data are turned on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

# Tool → the map layers (frontend layer ids) that show what it read.
TOOL_LAYERS: dict[str, tuple[str, ...]] = {
    "military_aircraft": ("military",),
    "chokepoints": ("chokepoints",),
    "situations": ("convergence",),
    "country": ("country-index",),
}
EVENT_FEEDS = {
    "earthquakes",
    "natural-events",
    "disaster-alerts",
    "conflict",
    "air-alerts",
    "internet-outages",
    "fires",
    "launches",
}


class StepLike(Protocol):
    @property
    def tool(self) -> str: ...
    @property
    def args(self) -> dict[str, Any]: ...
    @property
    def ok(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class MapFocus:
    lat: float | None
    lon: float | None
    zoom: float | None
    country: str | None
    layers: tuple[str, ...]


def _zoom(radius_km: float) -> float:
    return (
        7.0 if radius_km <= 100 else 6.0 if radius_km <= 300 else 5.0 if radius_km <= 800 else 4.0
    )


def focus_from(steps: Sequence[StepLike]) -> MapFocus | None:
    """The last place read (a point, else a country), and every layer that shows the data."""
    layers: list[str] = []
    point: tuple[float, float, float] | None = None
    country: str | None = None
    for step in steps:
        if not step.ok:
            continue
        args = step.args
        found = list(TOOL_LAYERS.get(step.tool, ()))
        if step.tool == "events" and args.get("feed") in EVENT_FEEDS:
            found.append(str(args["feed"]))
        for layer in found:
            if layer not in layers:
                layers.append(layer)
        try:
            lat, lon = float(args["lat"]), float(args["lon"])
        except (KeyError, TypeError, ValueError):
            pass
        else:
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                point = (lat, lon, _zoom(float(args.get("radius_km") or 300)))
        iso2 = args.get("iso2") if step.tool == "country" else None
        if isinstance(iso2, str) and len(iso2) == 2:
            country = iso2.upper()
    if point is None and country is None and not layers:
        return None
    return MapFocus(
        lat=point[0] if point else None,
        lon=point[1] if point else None,
        zoom=point[2] if point else None,
        country=None if point else country,
        layers=tuple(layers),
    )
