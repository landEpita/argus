"""RainViewer public radar composite, no key (https://www.rainviewer.com/api.html)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from argus.domain.imagery import RadarQuery, RasterLayer
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_URL = "https://api.rainviewer.com/public/weather-maps.json"
# 256 px tiles, colour scheme 2 ("universal blue"), smoothed, snow shown.
TILE_SUFFIX = "/256/{z}/{x}/{y}/2/1_1.png"
MAX_ZOOM = 7  # RainViewer's free tier stops serving detail beyond this


class RainViewerRadarFetcher(Fetcher[RadarQuery, RasterLayer]):
    provider_name = "rainviewer"

    def __init__(self, http: HttpClient, url: str = DEFAULT_URL) -> None:
        self._http = http
        self._url = url

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name)

    def transform(self, query: RadarQuery, raw: Any) -> RasterLayer:
        try:
            host = raw["host"]
            frame = raw["radar"]["past"][-1]
            return RasterLayer(
                id="weather-radar",
                label="Precipitation radar",
                tiles=(f"{host}{frame['path']}{TILE_SUFFIX}",),
                max_zoom=MAX_ZOOM,
                attribution="Radar © RainViewer",
                valid_at=datetime.fromtimestamp(frame["time"], tz=UTC),
                opacity=0.7,
            )
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderResponseError(self.provider_name, "no usable radar frame") from exc
