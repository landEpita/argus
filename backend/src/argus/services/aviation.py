"""Aviation service: the single entry point the API uses for aircraft."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from argus.domain.aviation import (
    AIRCRAFT_STATES,
    AIRCRAFT_TRACK,
    MILITARY_AIRCRAFT,
    Aircraft,
    AircraftQuery,
    AircraftTrack,
    TrackQuery,
)
from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, covering_circle
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError
from argus.providers.registry import ProviderRegistry

REGIONAL_RADIUS_NM = 250  # adsb.lol's limit, and a region one can reason about
WORLD_STALE_S = 3 * 3600.0  # an old snapshot, clearly labelled, beats an empty sky


class Coverage(StrEnum):
    BOX = "box"  # everything the providers report in the view
    WORLD = "world"  # a worldwide snapshot, filtered to the view
    REGIONAL = "regional"  # only a circle around the centre of the view


class WorldSnapshot(DomainModel):
    fetched_at: datetime
    items: tuple[Aircraft, ...]


@dataclass(frozen=True, slots=True)
class AircraftView:
    items: list[Aircraft]
    coverage: Coverage
    stale_age_s: float | None  # set when the world snapshot is older than it should be
    circle: tuple[float, float, float] | None  # (lat, lon, radius NM) when regional


def _around(lat: float, lon: float, radius_nm: float) -> BoundingBox:
    """The largest box inside the circle: adsb.lol measures the circle around the box."""
    half = radius_nm / math.sqrt(2) * 0.98
    dlat = half / 60.0
    dlon = half / max(60.0 * math.cos(math.radians(lat)), 1.0)
    return BoundingBox(
        west=max(-180, lon - dlon), south=max(-90, lat - dlat),
        east=min(180, lon + dlon), north=min(90, lat + dlat),
    )  # fmt: skip


_CODEC: PydanticCodec[list[Aircraft]] = PydanticCodec(list[Aircraft])
_WORLD: PydanticCodec[WorldSnapshot] = PydanticCodec(WorldSnapshot)
_TRACK_CODEC: PydanticCodec[AircraftTrack] = PydanticCodec(AircraftTrack)
TRACK_TTL_S = 30.0


class AviationService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Cache,
        ttl_s: float,
        military_ttl_s: float | None = None,
        world_ttl_s: float = 120.0,
        clock: WallClock | None = None,
    ) -> None:
        self._world_ttl_s = world_ttl_s
        self._clock = clock or SystemWallClock()
        self._registry = registry
        self._cache = cache
        self._ttl_s = ttl_s
        self._military_ttl_s = ttl_s if military_ttl_s is None else military_ttl_s

    async def aircraft(self, query: AircraftQuery) -> list[Aircraft]:
        return (await self.aircraft_view(query)).items

    async def aircraft_view(self, query: AircraftQuery) -> AircraftView:
        """
        Aircraft matching ``query``, and how complete and fresh they are.

        A view that fits 250 NM is asked of the providers directly (adsb.lol
        first: fresh and without a daily quota). A wider one is served from
        one worldwide OpenSky snapshot shared by every viewer; when OpenSky
        refuses (its anonymous quota lasts minutes), the last good snapshot is
        served with its age, else adsb.lol around the centre of the view.
        """
        bbox = query.bbox
        if bbox is not None and covering_circle(bbox)[2] <= REGIONAL_RADIUS_NM:
            upstream = AircraftQuery(bbox=bbox.expanded_to_grid(), include_on_ground=True)
            states = await self._fetch(AIRCRAFT_STATES, upstream, self._ttl_s)
            return AircraftView(self._filter(states, query), Coverage.BOX, None, None)
        try:
            snapshot = await get_or_set_with_fallback(
                self._cache, f"{AIRCRAFT_STATES.name}:world", self._world_ttl_s, WORLD_STALE_S,
                self._world, _WORLD, recoverable=(AllProvidersFailedError,),
            )  # fmt: skip
        except AllProvidersFailedError:
            if bbox is None:
                raise
            lat, lon, _ = covering_circle(bbox)
            around = _around(lat, lon, REGIONAL_RADIUS_NM)
            upstream = AircraftQuery(bbox=around, include_on_ground=True)
            states = await self._fetch(AIRCRAFT_STATES, upstream, self._ttl_s)
            return AircraftView(
                self._filter(states, query), Coverage.REGIONAL, None, (lat, lon, REGIONAL_RADIUS_NM)
            )
        age = (self._clock.utcnow() - snapshot.fetched_at).total_seconds()
        stale = age if age > self._world_ttl_s + 5 else None
        return AircraftView(self._filter(snapshot.items, query), Coverage.WORLD, stale, None)

    async def _world(self) -> WorldSnapshot:
        items = await self._registry.fetch(AIRCRAFT_STATES, AircraftQuery(include_on_ground=True))
        return WorldSnapshot(fetched_at=self._clock.utcnow(), items=tuple(items))

    def _filter(self, states: Sequence[Aircraft], query: AircraftQuery) -> list[Aircraft]:
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
