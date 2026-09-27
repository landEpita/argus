from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from argus.api.deps import EventsServiceDep
from argus.api.params import BBoxParam
from argus.domain.events import EventFeed, GeoEvent

router = APIRouter(prefix="/events", tags=["events"])


class EventCollection(BaseModel):
    feed: EventFeed
    count: int
    truncated: bool
    window_start: datetime
    items: list[GeoEvent]


class FeedInfo(BaseModel):
    feed: EventFeed
    providers: list[str]
    available: bool


@router.get("", response_model=list[FeedInfo])
def list_feeds(service: EventsServiceDep) -> list[FeedInfo]:
    """Every feed and whether a provider is configured for it (some need an API key)."""
    return [
        FeedInfo(feed=feed, providers=providers, available=bool(providers))
        for feed, providers in service.available_feeds().items()
    ]


@router.get("/{feed}", response_model=EventCollection)
async def list_events(
    feed: EventFeed,
    service: EventsServiceDep,
    bbox: BBoxParam,
    since_hours: Annotated[float, Query(gt=0, le=720)] = 24,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 2_000,
) -> EventCollection:
    """Events in the window, most severe first. Windows are capped per feed."""
    page = await service.events(feed, window=timedelta(hours=since_hours), bbox=bbox, limit=limit)
    return EventCollection(
        feed=page.feed,
        count=len(page.items),
        truncated=page.truncated,
        window_start=page.window_start,
        items=page.items,
    )
