"""
RSS / Atom reader (feedparser does the format quirks: RSS 0.9x-2.0, RDF, Atom).

Titles and summaries are reduced to plain text here: feeds carry HTML, and
nothing downstream should ever have to decide whether a string is markup.
"""

from __future__ import annotations

import calendar
import hashlib
import html
import re
from datetime import UTC, datetime
from typing import Any

import feedparser

from argus.domain.countries import CountryIndex, country_index
from argus.domain.news import Article, NewsSource
from argus.infra.http import HttpClient
from argus.providers.errors import ProviderResponseError

MAX_FEED_BYTES = 4 * 1024 * 1024
MAX_SUMMARY = 400
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(value: str | None, limit: int | None = None) -> str | None:
    if not value:
        return None
    text = _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", value))).strip()
    if limit and len(text) > limit:
        cut = text[: limit - 1]
        if text[limit - 1] != " ":  # the cut fell inside a word: drop the fragment
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip() + "…"
    return text or None


def _published(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    return None


class RssFeedReader:
    def __init__(self, http: HttpClient, countries: CountryIndex | None = None) -> None:
        self._http = http
        self._countries = countries or country_index()

    async def read(self, source: NewsSource) -> list[Article]:
        provider = f"news:{source.id}"
        body = await self._http.get_bytes(
            source.feed_url,
            provider=provider,
            headers={"Accept": "application/rss+xml, application/atom+xml, application/xml"},
            max_bytes=MAX_FEED_BYTES,
            timeout_s=20,
        )
        return self.parse(source, body)

    def parse(self, source: NewsSource, body: bytes) -> list[Article]:
        feed = feedparser.parse(body)
        if not feed.entries and feed.get("bozo"):
            raise ProviderResponseError(f"news:{source.id}", "not a readable RSS/Atom feed")
        articles: list[Article] = []
        for entry in feed.entries:
            title = plain_text(entry.get("title"))
            link = entry.get("link")
            when = _published(entry)
            if (
                not title
                or not isinstance(link, str)
                or not link.startswith(("http://", "https://"))
                or when is None
            ):
                continue
            summary = plain_text(entry.get("summary"), MAX_SUMMARY)
            articles.append(
                Article(
                    id=hashlib.sha1(link.encode()).hexdigest()[:20],  # noqa: S324 - an id, not security
                    source_id=source.id,
                    title=title,
                    url=link,
                    summary=summary,
                    published_at=when,
                    countries=self._countries.mentions(f"{title}. {summary or ''}"),
                )
            )
        return articles
