"""
The curated source list. Adding a source is adding a line; the labels are
part of the data and shown next to every story. Tiers and ownership are
editorial judgements — keep them justified and conservative.
"""

from __future__ import annotations

from argus.domain.news import NewsCategory, NewsSource, Ownership

W, D, C, R = NewsCategory.WORLD, NewsCategory.DEFENSE, NewsCategory.CYBER, NewsCategory.REGIONAL
PRIV, PUB, STATE, IGO = (
    Ownership.PRIVATE,
    Ownership.PUBLIC,
    Ownership.STATE,
    Ownership.INTERGOVERNMENTAL,
)


def _source(
    id: str,
    name: str,
    feed: str,
    home: str,
    category: NewsCategory,
    tier: int,
    ownership: Ownership,
    country: str | None,
) -> NewsSource:
    return NewsSource(
        id=id,
        name=name,
        feed_url=feed,
        homepage=home,
        category=category,
        tier=tier,
        ownership=ownership,
        country=country,
    )


DEFAULT_SOURCES: tuple[NewsSource, ...] = (
    _source(
        "bbc",
        "BBC News",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.bbc.com/news/world",
        W,
        1,
        PUB,
        "GB",
    ),
    _source(
        "dw",
        "Deutsche Welle",
        "https://rss.dw.com/rdf/rss-en-all",
        "https://www.dw.com/en",
        W,
        1,
        PUB,
        "DE",
    ),
    _source(
        "france24",
        "France 24",
        "https://www.france24.com/en/rss",
        "https://www.france24.com/en",
        W,
        1,
        PUB,
        "FR",
    ),
    _source(
        "npr",
        "NPR",
        "https://feeds.npr.org/1004/rss.xml",
        "https://www.npr.org/sections/world",
        W,
        1,
        PUB,
        "US",
    ),
    _source(
        "guardian",
        "The Guardian",
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/world",
        W,
        1,
        PRIV,
        "GB",
    ),
    _source(
        "un-news",
        "UN News",
        "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        "https://news.un.org",
        W,
        1,
        IGO,
        None,
    ),
    _source(
        "aljazeera",
        "Al Jazeera",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://www.aljazeera.com",
        W,
        2,
        STATE,
        "QA",
    ),
    _source(
        "kyiv-independent",
        "The Kyiv Independent",
        "https://kyivindependent.com/news-archive/rss/",
        "https://kyivindependent.com",
        R,
        2,
        PRIV,
        "UA",
    ),
    _source("tass", "TASS", "https://tass.com/rss/v2.xml", "https://tass.com", W, 3, STATE, "RU"),
    _source(
        "defense-news",
        "Defense News",
        "https://www.defensenews.com/arc/outboundfeeds/rss/",
        "https://www.defensenews.com",
        D,
        2,
        PRIV,
        "US",
    ),
    _source(
        "breaking-defense",
        "Breaking Defense",
        "https://breakingdefense.com/feed/",
        "https://breakingdefense.com",
        D,
        2,
        PRIV,
        "US",
    ),
    _source(
        "the-war-zone",
        "The War Zone",
        "https://www.twz.com/feed",
        "https://www.twz.com",
        D,
        2,
        PRIV,
        "US",
    ),
    _source(
        "bleepingcomputer",
        "BleepingComputer",
        "https://www.bleepingcomputer.com/feed/",
        "https://www.bleepingcomputer.com",
        C,
        2,
        PRIV,
        "US",
    ),
    _source(
        "the-record",
        "The Record",
        "https://therecord.media/feed",
        "https://therecord.media",
        C,
        2,
        PRIV,
        "US",
    ),
)
