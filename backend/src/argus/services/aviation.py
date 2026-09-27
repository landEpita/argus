"""Aviation service: the single entry point the API uses for aircraft."""

from __future__ import annotations

from argus.domain.aviation import (
    AIRCRAFT_STATES,
    AIRCRAFT_TRACK,
    MILITARY_AIRCRAFT,
    Aircraft,
    AircraftQuery,
    AircraftTrack,
    TrackQuery,
)
from argus.domain.capability import Capability
from argus.infra.cache import Cache
from argus.infra.codec import PydanticCodec
from argus.providers.registry import ProviderRegistry

_CODEC: PydanticCodec[list[Aircraft]] = PydanticCodec(list[Aircraft])
_TRACK_CODEC: PydanticCodec[AircraftTrack] = PydanticCodec(AircraftTrack)
TRACK_TTL_S = 30.0


class AviationService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Cache,
        ttl_s: float,
        military_ttl_s: float | None = None,
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._ttl_s = ttl_s
        self._military_ttl_s = ttl_s if military_ttl_s is None else military_ttl_s

    async def aircraft(self, query: AircraftQuery) -> list[Aircraft]:
        """
        Aircraft matching ``query``.

        Upstream is asked for a slightly larger, grid-aligned box so nearby
        viewports share a cache entry; the exact box and the on-ground rule
        are then applied here, identically for every provider.
        """
        upstream = AircraftQuery(
            bbox=query.bbox.expanded_to_grid() if query.bbox else None, include_on_ground=True
        )
        states = await self._fetch(AIRCRAFT_STATES, upstream, self._ttl_s)
        return [a for a in states if self._matches(a, query)]

    async def military(self, query: AircraftQuery) -> list[Aircraft]:
        """Military aircraft. The feed is worldwide, so one cache entry serves every box."""
        states = await self._fetch(
            MILITARY_AIRCRAFT, AircraftQuery(include_on_ground=True), self._military_ttl_s
        )
        return [a for a in states if self._matches(a, query)]

    async def track(self, icao24: str) -> AircraftTrack:
        query = TrackQuery(icao24=icao24.lower())
        return await self._cache.get_or_set(
            f"{AIRCRAFT_TRACK.name}:{query.icao24}",
            TRACK_TTL_S,
            lambda: self._registry.fetch(AIRCRAFT_TRACK, query),
            _TRACK_CODEC,
        )

    async def _fetch(
        self,
        capability: Capability[AircraftQuery, list[Aircraft]],
        upstream: AircraftQuery,
        ttl_s: float,
    ) -> list[Aircraft]:
        area = upstream.bbox.cache_key() if upstream.bbox else "world"
        return await self._cache.get_or_set(
            f"{capability.name}:{area}",
            ttl_s,
            lambda: self._registry.fetch(capability, upstream),
            _CODEC,
        )

    @staticmethod
    def _matches(aircraft: Aircraft, query: AircraftQuery) -> bool:
        if aircraft.on_ground and not query.include_on_ground:
            return False
        return query.bbox is None or query.bbox.contains(aircraft.position)
