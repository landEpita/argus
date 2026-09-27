from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from argus.api.deps import CyberServiceDep, NewsServiceDep, TelegramServiceDep
from argus.domain.countries import country_index
from argus.domain.cyber import ExploitedVulnerability
from argus.domain.geo import GeoPoint
from argus.domain.news import NewsCategory, NewsSource, Story
from argus.domain.telegram import TelegramPost
from argus.services.telegram import InvalidChannelError

router = APIRouter(prefix="/intel", tags=["intel"])


class SourceStatusOut(BaseModel):
    source: NewsSource
    articles: int
    error: str | None


class StoryCollection(BaseModel):
    count: int
    truncated: bool
    window_start: datetime
    items: list[Story]
    sources: list[SourceStatusOut]


class ChannelStatusOut(BaseModel):
    channel: str
    posts: int
    error: str | None


class TelegramCollection(BaseModel):
    count: int
    items: list[TelegramPost]
    channels: list[ChannelStatusOut]


class VulnerabilityCollection(BaseModel):
    count: int
    items: list[ExploitedVulnerability]


class CountryOut(BaseModel):
    iso2: str
    name: str
    centroid: GeoPoint
    region: str | None


@router.get("/news", response_model=StoryCollection)
async def news(
    service: NewsServiceDep,
    since_hours: Annotated[float, Query(gt=0, le=72)] = 24,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    category: NewsCategory | None = None,
    country: Annotated[str | None, Query(pattern=r"^[A-Za-z]{2}$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> StoryCollection:
    """Stories (grouped articles), newest first, with the status of every source."""
    page = await service.stories(
        window=timedelta(hours=since_hours),
        limit=limit,
        category=category,
        country=country,
        query=q,
    )
    return StoryCollection(
        count=len(page.items),
        truncated=page.truncated,
        window_start=page.window_start,
        items=page.items,
        sources=[
            SourceStatusOut(source=s.source, articles=s.articles, error=s.error)
            for s in page.sources
        ],
    )


@router.get("/news/sources", response_model=list[NewsSource])
def news_sources(service: NewsServiceDep) -> list[NewsSource]:
    """Every source with its tier and ownership, as shown next to stories."""
    return service.sources


@router.get("/telegram", response_model=TelegramCollection)
async def telegram(
    service: TelegramServiceDep,
    channels: Annotated[str, Query(description="Comma-separated public channel names")],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TelegramCollection:
    """Latest posts of public channels. Content is unverified by nature."""
    try:
        page = await service.posts(channels.split(","), limit)
    except InvalidChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TelegramCollection(
        count=len(page.items),
        items=page.items,
        channels=[
            ChannelStatusOut(channel=c.channel, posts=c.posts, error=c.error) for c in page.channels
        ],
    )


@router.get("/cyber/exploited", response_model=VulnerabilityCollection)
async def exploited(
    service: CyberServiceDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> VulnerabilityCollection:
    """Vulnerabilities added to CISA's exploited catalog in the last `days`."""
    items = await service.exploited(window=timedelta(days=days), limit=limit, query=q)
    return VulnerabilityCollection(count=len(items), items=items)


countries_router = APIRouter(prefix="/countries", tags=["countries"])


@countries_router.get("", response_model=list[CountryOut])
def countries() -> list[CountryOut]:
    """Country codes, names and centroids (for chips and fly-to)."""
    return [
        CountryOut(iso2=c.iso2, name=c.name, centroid=c.centroid, region=c.region)
        for c in sorted(country_index().all(), key=lambda c: c.name)
    ]
