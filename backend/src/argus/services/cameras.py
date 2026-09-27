"""
Open cameras across operator networks.

Catalogs change rarely, so each network is fetched once every few hours and
shared by every viewer; a network that fails keeps serving its last catalog
for a week. Only networks whose area overlaps the view are read, and a view
reports which networks it could not read instead of hiding them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from argus.domain.cameras import CAMERAS, NETWORKS, Camera, CameraNetwork, CameraQuery
from argus.domain.geo import BoundingBox
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.providers.registry import ProviderRegistry

_CODEC: PydanticCodec[list[Camera]] = PydanticCodec(list[Camera])
CATALOG_TTL_S = 6 * 3600.0
CATALOG_STALE_S = 7 * 86400.0


@dataclass(frozen=True, slots=True)
class CameraView:
    items: list[Camera]
    networks: list[CameraNetwork]
    unavailable: list[CameraNetwork]


class CameraService:
    def __init__(self, registry: ProviderRegistry, cache: Cache) -> None:
        self._registry = registry
        self._cache = cache

    async def cameras(
        self, bbox: BoundingBox | None, networks: set[CameraNetwork] | None = None
    ) -> CameraView:
        wanted = [
            n
            for n, info in NETWORKS.items()
            if (networks is None or n in networks)
            and (bbox is None or info.coverage.intersects(bbox))
        ]
        results = await asyncio.gather(*(self._catalog(n) for n in wanted))
        items: list[Camera] = []
        unavailable: list[CameraNetwork] = []
        for network, catalog in zip(wanted, results, strict=True):
            if catalog is None:
                unavailable.append(network)
            else:
                items.extend(c for c in catalog if bbox is None or bbox.contains(c.position))
        return CameraView(items, wanted, unavailable)

    async def _catalog(self, network: CameraNetwork) -> list[Camera] | None:
        capability = CAMERAS[network]
        try:
            return await get_or_set_with_fallback(
                self._cache, capability.name, CATALOG_TTL_S, CATALOG_STALE_S,
                lambda: self._registry.fetch(capability, CameraQuery()), _CODEC,
                recoverable=(AllProvidersFailedError,),
            )  # fmt: skip
        except (AllProvidersFailedError, NoProviderError):
            return None
