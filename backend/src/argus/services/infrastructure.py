"""
Facilities and cables: slow-changing data, cached for a day.

Facilities are fetched in fixed 5° tiles rather than per viewport: panning
reuses cached tiles, the public Overpass servers see a few small queries
instead of one per map move, and a slow tile does not block the others' cache.
"""

from __future__ import annotations

import asyncio
import math

from argus.domain.geo import BoundingBox
from argus.domain.infrastructure import (
    FACILITIES,
    SUBMARINE_CABLES,
    CableNetwork,
    CableQuery,
    Facility,
    FacilityKind,
    FacilityQuery,
)
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError
from argus.providers.registry import ProviderRegistry

_FACILITIES: PydanticCodec[list[Facility]] = PydanticCodec(list[Facility])
_CABLES: PydanticCodec[CableNetwork] = PydanticCodec(CableNetwork)
DAY_S = 86400.0
TILE_DEG = 5
MAX_TILES = 16  # 20° x 20°; beyond that the map should ask the user to zoom in
TILE_CONCURRENCY = 2  # be polite to volunteer-run servers


class TooManyTilesError(Exception):
    def __init__(self, tiles: int) -> None:
        super().__init__(f"view needs {tiles} tiles (max {MAX_TILES}): zoom in")
        self.tiles = tiles


def tiles_for(bbox: BoundingBox) -> list[BoundingBox]:
    """The fixed TILE_DEG grid cells covering ``bbox``."""
    west = math.floor(bbox.west / TILE_DEG) * TILE_DEG
    south = math.floor(bbox.south / TILE_DEG) * TILE_DEG
    east = math.ceil(bbox.east / TILE_DEG) * TILE_DEG
    north = math.ceil(bbox.north / TILE_DEG) * TILE_DEG
    east, north = max(east, west + TILE_DEG), max(north, south + TILE_DEG)
    return [
        BoundingBox(west=x, south=y, east=min(x + TILE_DEG, 180), north=min(y + TILE_DEG, 90))
        for x in range(west, min(east, 180), TILE_DEG)
        for y in range(south, min(north, 90), TILE_DEG)
    ]


class InfrastructureService:
    def __init__(self, registry: ProviderRegistry, cache: Cache) -> None:
        self._registry = registry
        self._cache = cache

        self._semaphore = asyncio.Semaphore(TILE_CONCURRENCY)

    async def facilities(self, kind: FacilityKind, bbox: BoundingBox) -> list[Facility]:
        tiles = tiles_for(bbox)
        if len(tiles) > MAX_TILES:
            raise TooManyTilesError(len(tiles))
        per_tile = await asyncio.gather(*(self._tile(kind, tile) for tile in tiles))
        seen: set[str] = set()
        found: list[Facility] = []
        for facility in (f for tile in per_tile for f in tile):
            # A way straddling a tile edge is returned by both tiles.
            if facility.id not in seen and bbox.contains(facility.position):
                seen.add(facility.id)
                found.append(facility)
        return found

    async def _tile(self, kind: FacilityKind, tile: BoundingBox) -> list[Facility]:
        query = FacilityQuery(kind=kind, bbox=tile)

        async def fetch() -> list[Facility]:
            async with self._semaphore:
                return await self._registry.fetch(FACILITIES, query)

        return await get_or_set_with_fallback(
            self._cache,
            f"{FACILITIES.name}:{kind.value}:{tile.west:g},{tile.south:g}",
            DAY_S,
            7 * DAY_S,
            fetch,
            _FACILITIES,
            recoverable=(AllProvidersFailedError,),
        )

    async def cables(self) -> CableNetwork:
        return await get_or_set_with_fallback(
            self._cache,
            SUBMARINE_CABLES.name,
            DAY_S,
            7 * DAY_S,
            lambda: self._registry.fetch(SUBMARINE_CABLES, CableQuery()),
            _CABLES,
            recoverable=(AllProvidersFailedError,),
        )
