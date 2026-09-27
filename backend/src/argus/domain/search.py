"""
Hybrid search over what Argus has read (news stories, Telegram posts).

Lexical ranking is BM25 over accent-folded words; semantic ranking, when an
embedding model is configured, is cosine similarity. The two are merged with
reciprocal rank fusion, which needs no score calibration between them.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60

# Very common words in the languages of the questions and the feeds.
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "de",
        "des",
        "du",
        "en",
        "et",
        "for",
        "from",
        "in",
        "is",
        "it",
        "la",
        "le",
        "les",
        "of",
        "on",
        "or",
        "que",
        "qui",
        "the",
        "to",
        "un",
        "une",
        "with",
        "sur",
        "dans",
        "pour",
        "par",
        "au",
        "aux",
        "est",
        "ce",
        "il",
        "se",
    ]
)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


class DocKind(StrEnum):
    STORY = "story"
    POST = "post"


class Document(DomainModel):
    id: str
    kind: DocKind
    title: str
    text: str = ""
    source: str
    url: str
    at: datetime
    unverified: bool = Field(description="Telegram posts and state-media-only stories")


class Match(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    BOTH = "both"


class Hit(DomainModel):
    document: Document
    score: float
    match: Match


def fold(text: str) -> str:
    """Lowercase without accents: 'Élysée' and 'elysee' are the same word."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(fold(text)) if w not in STOPWORDS and len(w) > 1]


def bm25(query: str, documents: Sequence[Document]) -> list[tuple[str, float]]:
    """(document id, score) for documents sharing at least one query word, best first."""
    terms = set(tokens(query))
    if not terms or not documents:
        return []
    bags = {d.id: Counter(tokens(f"{d.title} {d.title} {d.text}")) for d in documents}
    lengths = {i: sum(b.values()) for i, b in bags.items()}
    avg = sum(lengths.values()) / len(lengths) or 1.0
    n = len(documents)
    idf = {
        t: math.log(1 + (n - df + 0.5) / (df + 0.5))
        for t in terms
        if (df := sum(1 for b in bags.values() if t in b))
    }
    scores: list[tuple[str, float]] = []
    for doc_id, bag in bags.items():
        score = 0.0
        for t, w in idf.items():
            f = bag.get(t, 0)
            if f:
                norm = f + BM25_K1 * (1 - BM25_B + BM25_B * lengths[doc_id] / avg)
                score += w * f * (BM25_K1 + 1) / norm
        if score > 0:
            scores.append((doc_id, score))
    return sorted(scores, key=lambda s: s[1], reverse=True)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic(
    query_vector: Sequence[float], vectors: Mapping[str, Sequence[float]], floor: float
) -> list[tuple[str, float]]:
    ranked = [(i, cosine(query_vector, v)) for i, v in vectors.items()]
    return sorted((r for r in ranked if r[1] >= floor), key=lambda r: r[1], reverse=True)


def fuse(
    documents: Mapping[str, Document],
    lexical: Sequence[tuple[str, float]],
    semantic_: Sequence[tuple[str, float]],
    limit: int,
) -> list[Hit]:
    """Reciprocal rank fusion: 1/(k + rank) summed over the rankings a document is in."""
    scores: dict[str, float] = {}
    lex = {doc_id for doc_id, _ in lexical}
    sem = {doc_id for doc_id, _ in semantic_}
    for ranking in (lexical, semantic_):
        for rank, (doc_id, _) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (RRF_K + rank)
    best = sorted(scores.items(), key=lambda s: s[1], reverse=True)[:limit]
    return [
        Hit(
            document=documents[doc_id],
            score=round(score, 5),
            match=Match.BOTH if doc_id in lex and doc_id in sem
            else Match.LEXICAL if doc_id in lex else Match.SEMANTIC,
        )
        for doc_id, score in best
    ]  # fmt: skip
