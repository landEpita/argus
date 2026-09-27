"""Raster tile layers (radar, satellite imagery) the map can overlay."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability


class RasterLayer(DomainModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    tiles: tuple[str, ...] = Field(description="XYZ URL templates ({z}/{x}/{y})")
    tile_size: int = 256
    min_zoom: int = 0
    max_zoom: int = Field(description="Deepest zoom the source serves; the map overzooms beyond")
    attribution: str
    valid_at: datetime | None = Field(default=None, description="Observation time of the imagery")
    opacity: float = Field(default=1.0, ge=0, le=1)


class RadarQuery(DomainModel):
    pass


WEATHER_RADAR: Capability[RadarQuery, RasterLayer] = Capability(
    "imagery.weather_radar", "Latest composite precipitation radar frame."
)
