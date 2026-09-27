"""
Raster overlays: radar from a capability, NASA GIBS imagery computed locally.

GIBS tile URLs are deterministic (layer + date), so they need no upstream
call; the date is yesterday in UTC, the latest day reliably complete.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from argus.domain.imagery import WEATHER_RADAR, RadarQuery, RasterLayer
from argus.infra.cache import Cache
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

_CODEC: PydanticCodec[RasterLayer] = PydanticCodec(RasterLayer)
RADAR_TTL_S = 300.0
GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
GIBS_ATTRIBUTION = "Imagery: NASA EOSDIS GIBS"


def gibs_layers(day: datetime) -> list[RasterLayer]:
    date = day.date().isoformat()
    valid_at = datetime.combine(day.date(), time(12), tzinfo=day.tzinfo)
    return [
        RasterLayer(
            id="satellite-true-color",
            label="Satellite imagery (VIIRS, yesterday)",
            tiles=(
                f"{GIBS}/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/{date}"
                "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
            ),
            max_zoom=9,
            attribution=GIBS_ATTRIBUTION,
            valid_at=valid_at,
        ),
        RasterLayer(
            id="night-lights",
            label="Night lights (VIIRS, yesterday)",
            tiles=(
                f"{GIBS}/VIIRS_SNPP_DayNightBand_At_Sensor_Radiance/default/{date}"
                "/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png",
            ),
            max_zoom=8,
            attribution=GIBS_ATTRIBUTION,
            valid_at=valid_at,
            opacity=0.9,
        ),
    ]


class ImageryService:
    def __init__(
        self, registry: ProviderRegistry, cache: Cache, clock: WallClock | None = None
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._clock = clock or SystemWallClock()

    async def layers(self) -> list[RasterLayer]:
        """Every overlay currently available. A failing radar does not hide the others."""
        layers = gibs_layers(self._clock.utcnow() - timedelta(days=1))
        try:
            radar = await self._cache.get_or_set(
                WEATHER_RADAR.name,
                RADAR_TTL_S,
                lambda: self._registry.fetch(WEATHER_RADAR, RadarQuery()),
                _CODEC,
            )
        except (AllProvidersFailedError, NoProviderError) as exc:
            logger.warning("radar unavailable", extra={"error": str(exc)})
        else:
            layers.insert(0, radar)
        return layers
