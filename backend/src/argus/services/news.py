"""
News: fetch every source (cached per source), group into stories, filter.

Sources fail independently: one dead feed never empties the panel. Each
source's health is tracked under ``news:<id>`` so the UI can say which
outlets are missing from the picture.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.domain.news import Article, FeedReader, NewsCategory, NewsSource, Story
from argus.domain.stories import cluster
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.codec import PydanticCodec
from argus.infra.health import HealthRegistry
from argus.providers.errors import ProviderError

logger = logging.getLogger(__name__)

_CODEC: PydanticCodec[list[Article]] = PydanticCodec(list[Article])
SOURCE_TTL_S = 300.0
SOURCE_STALE_TTL_S = 86400.0
CONCURRENCY = 6
MAX_FUTURE_SKEW = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class SourceStatus:
    source: NewsSource
    articles: int
    error: str | None


@dataclass(frozen=True, slots=True)
class StoryPage:
    items: list[Story]
    truncated: bool
    window_start: datetime
    sources: list[SourceStatus]


class NewsService:
    def __init__(
        self,
        reader: FeedReader,
        sources: Sequence[NewsSource],
        cache: Cache,
        health: HealthRegistry,
        clock: WallClock | None = None,
    ) -> None:
        self._reader = reader
        self._sources = {s.id: s for s in sources}
        self._cache = cache
        self._health = health
        self._clock = clock or SystemWallClock()
        self._semaphore = asyncio.Semaphore(CONCURRENCY)
        for source in sources:
            health.register(self._provider(source))

    @property
    def sources(self) -> list[NewsSource]:
        return list(self._sources.values())

    async def stories(
        self,
        *,
        window: timedelta,
        limit: int,
        category: NewsCategory | None = None,
        country: str | None = None,
        query: str | None = None,
    ) -> StoryPage:
        now = self._clock.utcnow()
        since = now - window
        statuses = await asyncio.gather(*(self._collect(s) for s in self._sources.values()))
        articles = {
            a.url: a
            for status, fetched in statuses
            for a in fetched
            if since <= a.published_at <= now + MAX_FUTURE_SKEW
        }
        stories = cluster(articles.values(), self._sources)
        needle = query.casefold().strip() if query else None
        matching = [
            s
            for s in stories
            if (category is None or s.category is category)
            and (country is None or country.upper() in s.countries)
            and (needle is None or any(needle in a.title.casefold() for a in s.articles))
        ]
        matching.sort(key=lambda s: (s.last_updated, len(s.sources)), reverse=True)
        return StoryPage(
            items=matching[:limit],
            truncated=len(matching) > limit,
            window_start=since,
            sources=[status for status, _ in statuses],
        )

    async def _collect(self, source: NewsSource) -> tuple[SourceStatus, list[Article]]:
        async def fetch() -> list[Article]:
            async with self._semaphore:
                articles = await self._reader.read(source)
            self._health.record_success(self._provider(source))
            return articles

        try:
            articles = await get_or_set_with_fallback(
                self._cache,
                f"news:{source.id}",
                SOURCE_TTL_S,
                SOURCE_STALE_TTL_S,
                fetch,
                _CODEC,
                recoverable=(ProviderError,),
            )
        except ProviderError as exc:
            logger.warning("news source failed", extra={"source": source.id, "error": str(exc)})
            self._health.record_failure(self._provider(source), str(exc))
            return SourceStatus(source, 0, str(exc)), []
        return SourceStatus(source, len(articles), None), articles

    @staticmethod
    def _provider(source: NewsSource) -> str:
        return f"news:{source.id}"
