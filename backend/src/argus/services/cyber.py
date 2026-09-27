from __future__ import annotations

from datetime import timedelta

from argus.domain.cyber import EXPLOITED_VULNERABILITIES, ExploitedVulnerability, KevQuery
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError
from argus.providers.registry import ProviderRegistry

_CODEC: PydanticCodec[list[ExploitedVulnerability]] = PydanticCodec(list[ExploitedVulnerability])
KEV_TTL_S = 6 * 3600.0  # CISA updates the catalog a few times a week


class CyberService:
    def __init__(
        self, registry: ProviderRegistry, cache: Cache, clock: WallClock | None = None
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._clock = clock or SystemWallClock()

    async def exploited(
        self, *, window: timedelta, limit: int, query: str | None = None
    ) -> list[ExploitedVulnerability]:
        catalog = await get_or_set_with_fallback(
            self._cache,
            EXPLOITED_VULNERABILITIES.name,
            KEV_TTL_S,
            7 * 86400.0,
            lambda: self._registry.fetch(EXPLOITED_VULNERABILITIES, KevQuery()),
            _CODEC,
            recoverable=(AllProvidersFailedError,),
        )
        since = (self._clock.utcnow() - window).date()
        needle = query.casefold() if query else None
        recent = [
            v
            for v in catalog
            if v.date_added >= since
            and (needle is None or needle in f"{v.cve} {v.vendor} {v.product} {v.name}".casefold())
        ]
        recent.sort(key=lambda v: (v.date_added, v.cve), reverse=True)
        return recent[:limit]
