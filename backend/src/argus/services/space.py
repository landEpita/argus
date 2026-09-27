"""Satellite positions: cached elements, propagated at request time."""

from __future__ import annotations

import logging
from datetime import datetime

from argus.domain.geo import GeoPoint
from argus.domain.orbit import PropagationError, build_satrec, propagate
from argus.domain.space import (
    ORBITAL_ELEMENTS,
    ElementsQuery,
    OrbitalElements,
    SatelliteGroup,
    SatellitePosition,
)
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError
from argus.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

_CODEC: PydanticCodec[list[OrbitalElements]] = PydanticCodec(list[OrbitalElements])
ELEMENTS_TTL_S = 2 * 3600  # CelesTrak's requested maximum refresh rate
STALE_ELEMENTS_TTL_S = 3 * 86400  # served if CelesTrak refuses (it 403s re-downloads < 2 h)
MAX_ELEMENT_AGE_DAYS = 30  # older elements are too inaccurate to plot


class SpaceService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Cache,
        clock: WallClock | None = None,
        elements_ttl_s: float = ELEMENTS_TTL_S,
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._clock = clock or SystemWallClock()
        self._ttl_s = elements_ttl_s

    async def positions(
        self, group: SatelliteGroup, at: datetime | None = None
    ) -> list[SatellitePosition]:
        at = at or self._clock.utcnow()
        query = ElementsQuery(group=group)
        elements = await get_or_set_with_fallback(
            self._cache,
            f"{ORBITAL_ELEMENTS.name}:{group.value}",
            self._ttl_s,
            STALE_ELEMENTS_TTL_S,
            lambda: self._registry.fetch(ORBITAL_ELEMENTS, query),
            _CODEC,
            recoverable=(AllProvidersFailedError,),
        )
        positions: list[SatellitePosition] = []
        skipped = 0
        for element in elements:
            age_days = (at - element.epoch).total_seconds() / 86400
            if abs(age_days) > MAX_ELEMENT_AGE_DAYS:
                skipped += 1
                continue
            try:
                state = propagate(build_satrec(element), at)
            except PropagationError:
                skipped += 1
                continue
            positions.append(
                SatellitePosition(
                    norad_id=element.norad_id,
                    name=element.name,
                    group=group,
                    position=GeoPoint(
                        lat=state.geodetic.lat_deg,
                        lon=(state.geodetic.lon_deg + 180) % 360 - 180,
                    ),
                    altitude_km=round(state.geodetic.alt_km, 1),
                    speed_kms=round(state.speed_kms, 3),
                    at=at,
                    elements_age_days=round(age_days, 2),
                )
            )
        if skipped:
            logger.info("skipped satellites", extra={"group": group.value, "count": skipped})
        return positions
