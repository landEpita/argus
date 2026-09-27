"""
Event feeds: one service, a table of per-feed policies.

Each feed says how long it may be cached, how far back it can look, and
whether its upstream accepts a bounding box (FIRMS does; USGS summary feeds
are global). The exact box and time window are always applied here, so every
provider behaves the same.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.domain.events import FEED_CAPABILITIES, EventFeed, EventQuery, GeoEvent
from argus.domain.geo import BoundingBox
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError
from argus.providers.registry import ProviderRegistry

_CODEC: PydanticCodec[list[GeoEvent]] = PydanticCodec(list[GeoEvent])


@dataclass(frozen=True, slots=True)
class FeedPolicy:
    ttl_s: float
    max_window: timedelta
    upstream_bbox: bool = False
    # Keep the last good answer this long and serve it when the upstream fails
    # (for rate-limited feeds: Launch Library allows 15 anonymous calls per hour).
    stale_ttl_s: float | None = None


FEED_POLICIES: dict[EventFeed, FeedPolicy] = {
    EventFeed.EARTHQUAKES: FeedPolicy(ttl_s=60, max_window=timedelta(days=30)),
    EventFeed.NATURAL_EVENTS: FeedPolicy(ttl_s=900, max_window=timedelta(days=30)),
    EventFeed.DISASTER_ALERTS: FeedPolicy(ttl_s=900, max_window=timedelta(days=30)),
    EventFeed.FIRES: FeedPolicy(ttl_s=900, max_window=timedelta(days=5), upstream_bbox=True),
    EventFeed.CONFLICT: FeedPolicy(ttl_s=300, max_window=timedelta(hours=24)),
    EventFeed.AIR_ALERTS: FeedPolicy(ttl_s=30, max_window=timedelta(hours=1)),
    EventFeed.INTERNET_OUTAGES: FeedPolicy(ttl_s=600, max_window=timedelta(days=7)),
    EventFeed.LAUNCHES: FeedPolicy(
        ttl_s=3600, max_window=timedelta(days=30), stale_ttl_s=3 * 86400
    ),
}


@dataclass(frozen=True, slots=True)
class EventPage:
    feed: EventFeed
    items: list[GeoEvent]
    truncated: bool
    window_start: datetime


class EventsService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Cache,
        clock: WallClock | None = None,
        policies: dict[EventFeed, FeedPolicy] | None = None,
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._clock = clock or SystemWallClock()
        self._policies = policies or FEED_POLICIES

    def available_feeds(self) -> dict[EventFeed, list[str]]:
        return {
            feed: self._registry.providers_for(capability)
            for feed, capability in FEED_CAPABILITIES.items()
        }

    async def events(
        self, feed: EventFeed, *, window: timedelta, bbox: BoundingBox | None, limit: int
    ) -> EventPage:
        policy = self._policies[feed]
        window = min(window, policy.max_window)
        now = self._clock.utcnow()
        since = now - window

        # Ask upstream from a bucketed start time so requests within one TTL
        # share a cache entry; the exact window is applied below.
        bucket_s = max(int(policy.ttl_s), 60)
        bucketed = datetime.fromtimestamp(since.timestamp() // bucket_s * bucket_s, tz=since.tzinfo)
        upstream_bbox = bbox.expanded_to_grid() if bbox and policy.upstream_bbox else None
        area = upstream_bbox.cache_key() if upstream_bbox else "world"
        capability = FEED_CAPABILITIES[feed]
        upstream = EventQuery(bbox=upstream_bbox, since=bucketed)

        key = f"{capability.name}:{area}:{int(bucketed.timestamp())}"

        def factory() -> Awaitable[list[GeoEvent]]:
            return self._registry.fetch(capability, upstream)

        if policy.stale_ttl_s is None:
            events = await self._cache.get_or_set(key, policy.ttl_s, factory, _CODEC)
        else:
            events = await get_or_set_with_fallback(
                self._cache,
                key,
                policy.ttl_s,
                policy.stale_ttl_s,
                factory,
                _CODEC,
                recoverable=(AllProvidersFailedError,),
                stale_key=f"{capability.name}:{area}:last-good",
            )
        matching = [
            e
            for e in events
            if e.occurred_at >= since and (bbox is None or bbox.contains(e.position))
        ]
        # Most severe first, so a truncated page keeps what matters.
        matching.sort(key=lambda e: (e.severity or 0.0, e.occurred_at), reverse=True)
        return EventPage(
            feed=feed, items=matching[:limit], truncated=len(matching) > limit, window_start=since
        )
