"""
Grouping articles into stories — pure, deterministic, dependency-free.

Two articles belong to the same story when their title vocabularies overlap
enough (Jaccard similarity on content words, with named countries as extra
tokens) and they were published close in time. Greedy single pass in time
order: cheap for the few hundred articles a refresh brings, and stable, so a
story does not reshuffle between refreshes.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from argus.domain.news import Article, NewsSource, Ownership, Story, StorySource

SIMILARITY_THRESHOLD = 0.3
MAX_GAP = timedelta(hours=36)
_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9']+")
# A word list reads better as one string than as 90 quoted items.
STOPWORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or over says said
    say that the their this to up was were will with after amid against about new more than
    not but who what why how when where us un could would should may might just also been
    being first last out off down year years day days week weeks live latest update updates
    report reports video watch""".split()  # noqa: SIM905
)


def tokens(article: Article) -> frozenset[str]:
    words = {w.lower().strip("'") for w in _WORD.findall(article.title)}
    content = {w for w in words if len(w) > 2 and w not in STOPWORDS}
    return frozenset(content | {f"@{c}" for c in article.countries})


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class _Cluster:
    articles: list[Article] = field(default_factory=list)
    vocabulary: list[frozenset[str]] = field(default_factory=list)

    def similarity(self, candidate: frozenset[str]) -> float:
        # Best match against members: a story's wording drifts as it develops.
        return max(jaccard(candidate, v) for v in self.vocabulary)

    @property
    def last(self) -> datetime:
        return max(a.published_at for a in self.articles)


def cluster(
    articles: Iterable[Article],
    sources: Mapping[str, NewsSource],
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[Story]:
    clusters: list[_Cluster] = []
    for article in sorted(articles, key=lambda a: (a.published_at, a.id)):
        vocab = tokens(article)
        best: _Cluster | None = None
        best_score = threshold
        for c in clusters:
            if article.published_at - c.last > MAX_GAP:
                continue
            if any(
                a.source_id == article.source_id and a.title == article.title for a in c.articles
            ):
                best = c
                break
            score = c.similarity(vocab)
            if score >= best_score:
                best, best_score = c, score
        if best is None:
            best = _Cluster()
            clusters.append(best)
        best.articles.append(article)
        best.vocabulary.append(vocab)
    return [_to_story(c, sources) for c in clusters]


def _to_story(c: _Cluster, sources: Mapping[str, NewsSource]) -> Story:
    articles = sorted(c.articles, key=lambda a: a.published_at)
    known = [sources[a.source_id] for a in articles if a.source_id in sources]
    # Title from the most reliable outlet, earliest first among equals.
    lead = min(
        articles,
        key=lambda a: (sources[a.source_id].tier if a.source_id in sources else 9, a.published_at),
    )
    unique_sources: dict[str, NewsSource] = {s.id: s for s in known}
    countries: dict[str, int] = {}
    for a in articles:
        for code in a.countries:
            countries[code] = countries.get(code, 0) + 1
    return Story(
        id=hashlib.sha1(articles[0].id.encode()).hexdigest()[:16],  # noqa: S324 - an id, not security
        title=lead.title,
        url=lead.url,
        articles=tuple(articles),
        sources=tuple(
            StorySource(id=s.id, name=s.name, tier=s.tier, ownership=s.ownership)
            for s in sorted(unique_sources.values(), key=lambda s: (s.tier, s.name))
        ),
        first_seen=articles[0].published_at,
        last_updated=articles[-1].published_at,
        countries=tuple(sorted(countries, key=lambda k: -countries[k])),
        category=sources[lead.source_id].category
        if lead.source_id in sources
        else known[0].category,
        state_media_only=bool(unique_sources)
        and all(s.ownership is Ownership.STATE for s in unique_sources.values()),
    )
