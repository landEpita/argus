"""
News: sources with an explicit editorial profile, articles, and stories
(clusters of articles about the same thing).

Every source carries two independent labels, both shown to the user:
- ``tier`` — editorial track record: 1 = established newsroom or
  intergovernmental body, 2 = specialist or regional outlet, 3 = outlet under
  direct state control of a government without press freedom;
- ``ownership`` — who funds and controls it. "public" (BBC, DW) is not "state":
  public broadcasters are editorially independent by charter; "state" outlets
  are not.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from argus.domain.base import DomainModel


class Ownership(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"
    STATE = "state"
    INTERGOVERNMENTAL = "intergovernmental"


class NewsCategory(StrEnum):
    WORLD = "world"
    DEFENSE = "defense"
    CYBER = "cyber"
    REGIONAL = "regional"


class NewsSource(DomainModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    feed_url: str
    homepage: str
    category: NewsCategory
    tier: int = Field(ge=1, le=3)
    ownership: Ownership
    country: str | None = Field(default=None, description="ISO2 of the owning state or HQ")


class Article(DomainModel):
    id: str
    source_id: str
    title: str
    url: str
    summary: str | None = None
    published_at: datetime
    countries: tuple[str, ...] = ()


class StorySource(DomainModel):
    id: str
    name: str
    tier: int
    ownership: Ownership


class Story(DomainModel):
    id: str
    title: str
    url: str = Field(description="Link of the article the title comes from")
    articles: tuple[Article, ...]
    sources: tuple[StorySource, ...]
    first_seen: datetime
    last_updated: datetime
    countries: tuple[str, ...]
    category: NewsCategory
    state_media_only: bool = Field(description="Only state-controlled outlets report this")


class FeedReader(Protocol):
    """Port: fetch one source's current items."""

    async def read(self, source: NewsSource) -> list[Article]: ...
