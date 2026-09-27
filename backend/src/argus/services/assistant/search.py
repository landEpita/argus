"""
Search over what Argus has read: the last days of news stories and the
owner's Telegram channels. Keywords always; meaning too when an embedding
model is configured (then the two rankings are fused).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from argus.adapters.llm.embeddings import Embedded
from argus.domain.llm import UsageRecord, UsageRepository
from argus.domain.news import Story
from argus.domain.search import DocKind, Document, Hit, bm25, fuse, semantic
from argus.domain.telegram import TelegramPost
from argus.infra.clock import WallClock
from argus.providers.errors import AllProvidersFailedError, NoProviderError, ProviderError

SEMANTIC_FLOOR = 0.45
VECTOR_CACHE = 5000
CORPUS_STORIES = 400
CORPUS_POSTS = 200


class Embedder(Protocol):
    async def embed(self, owner: str, texts: list[str]) -> Embedded | None: ...


class StorySource(Protocol):
    async def recent(self, hours: float, limit: int) -> list[Story]: ...


class PostSource(Protocol):
    async def recent(self, owner: str, limit: int) -> list[TelegramPost]: ...


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[Hit]
    semantic: bool
    corpus: int
    note: str | None = None


def story_document(s: Story) -> Document:
    return Document(
        id=f"story:{s.id}",
        kind=DocKind.STORY,
        title=s.title,
        text=" ".join(a.title for a in s.articles[1:6]),
        source=", ".join(src.name for src in s.sources[:3]),
        url=s.url,
        at=s.last_updated,
        unverified=s.state_media_only,
    )


def post_document(p: TelegramPost) -> Document:
    text = p.text or ""
    return Document(
        id=f"post:{p.id}",
        kind=DocKind.POST,
        title=text[:140] or "(media only)",
        text=text,
        source=f"Telegram @{p.channel}",
        url=p.url,
        at=p.published_at,
        unverified=True,
    )


class SearchService:
    def __init__(
        self,
        stories: StorySource,
        posts: PostSource,
        embedder: Embedder,
        clock: WallClock,
        usage: UsageRepository | None = None,
    ) -> None:
        self._stories = stories
        self._posts = posts
        self._embedder = embedder
        self._clock = clock
        self._usage = usage
        self._vectors: OrderedDict[str, list[float]] = OrderedDict()

    async def search(
        self, owner: str, query: str, *, hours: float = 72, limit: int = 8
    ) -> SearchResult:
        documents: list[Document] = []
        notes: list[str] = []
        try:
            documents += [
                story_document(s) for s in await self._stories.recent(hours, CORPUS_STORIES)
            ]
        except (NoProviderError, AllProvidersFailedError):
            notes.append("news unavailable")
        try:
            documents += [post_document(p) for p in await self._posts.recent(owner, CORPUS_POSTS)]
        except (NoProviderError, AllProvidersFailedError):
            notes.append("Telegram unavailable")
        by_id = {d.id: d for d in documents}
        lexical = bm25(query, documents)
        meaning: list[tuple[str, float]] = []
        used_semantic = False
        try:
            found = await self._vectors_for(owner, query, by_id)
        except ProviderError as exc:
            notes.append(f"semantic search failed: {exc}")
            found = None
        if found is not None:
            query_vector, vectors = found
            meaning = semantic(query_vector, vectors, SEMANTIC_FLOOR)
            used_semantic = True
        return SearchResult(
            hits=fuse(by_id, lexical, meaning, limit),
            semantic=used_semantic,
            corpus=len(documents),
            note="; ".join(notes) or None,
        )

    async def _vectors_for(
        self, owner: str, query: str, documents: dict[str, Document]
    ) -> tuple[list[float], dict[str, list[float]]] | None:
        """The query's vector and the documents', embedding only those not cached yet."""
        missing = [i for i in documents if i not in self._vectors]
        texts = [query] + [f"{documents[i].title}. {documents[i].text[:500]}" for i in missing]
        result = await self._embedder.embed(owner, texts)
        if result is None:
            return None
        await self._record(owner, result)
        for doc_id, vector in zip(missing, result.vectors[1:], strict=True):
            self._vectors[doc_id] = vector
            if len(self._vectors) > VECTOR_CACHE:
                self._vectors.popitem(last=False)
        vectors = {i: v for i in documents if (v := self._vectors.get(i)) is not None}
        return result.vectors[0], vectors

    async def _record(self, owner: str, result: Embedded) -> None:
        if self._usage is None or not result.input_tokens:
            return
        await self._usage.add(
            UsageRecord(
                owner=owner, at=self._clock.utcnow(), purpose="embed", provider="embeddings",
                model=result.model, input_tokens=result.input_tokens, output_tokens=0,
                cost_usd=result.cost_usd,
            )
        )  # fmt: skip
