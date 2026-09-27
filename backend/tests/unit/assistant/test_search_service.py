from datetime import UTC, datetime
from typing import Any

import pytest

from argus.adapters.llm.embeddings import Embedded, LiteLLMEmbedder
from argus.domain.llm import LlmConfig, ModelUsage, UsageRecord
from argus.domain.search import Match
from argus.domain.telegram import TelegramPost
from argus.providers.errors import (
    AllProvidersFailedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from argus.services.assistant.search import SearchService
from argus.services.assistant.tools import Toolbox, ToolContext, ToolError
from tests.fakes import FakeWallClock
from tests.unit.domain.test_signals import story

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


def titled(i: str, title: str) -> Any:
    return story(i, ("YE",), 2).model_copy(update={"title": title})


class Stories:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def recent(self, hours: float, limit: int) -> list[Any]:
        if self.fail:
            raise AllProvidersFailedError("news", [])
        return [
            titled("1", "Houthi missile hits tanker in Red Sea"),
            titled("2", "Paris election results"),
        ]


class Posts:
    async def recent(self, owner: str, limit: int) -> list[TelegramPost]:
        return [
            TelegramPost(
                id="osint/9", channel="osint", text="Explosions near Hodeidah port",
                published_at=NOW, url="https://t.me/osint/9",
            )
        ]  # fmt: skip


class Meaning:
    """Toy embeddings: 'sea' and 'port' texts point one way, the rest another."""

    def __init__(self, on: bool = True, error: Exception | None = None) -> None:
        self.on, self.error = on, error
        self.batches: list[list[str]] = []

    async def embed(self, owner: str, texts: list[str]) -> Embedded | None:
        if self.error:
            raise self.error
        if not self.on:
            return None
        self.batches.append(texts)
        vectors = [
            [1.0, 0.0] if any(w in t.lower() for w in ("sea", "port", "mer")) else [0.0, 1.0]
            for t in texts
        ]
        return Embedded(vectors, "ollama/nomic-embed-text", 12 * len(texts), 0.0)


class Usage:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def add(self, record: UsageRecord) -> None:
        self.records.append(record)

    async def summary(self, owner: str, since: datetime) -> list[ModelUsage]:
        return []


async def test_keywords_only_without_an_embedding_model() -> None:
    svc = SearchService(Stories(), Posts(), Meaning(on=False), FakeWallClock(NOW))
    result = await svc.search("local", "Red Sea tanker")
    assert result.semantic is False
    assert result.corpus == 3
    assert [(h.document.id, h.match) for h in result.hits] == [("story:1", Match.LEXICAL)]


async def test_meaning_finds_what_words_miss_and_vectors_are_cached() -> None:
    meaning, usage = Meaning(), Usage()
    svc = SearchService(Stories(), Posts(), meaning, FakeWallClock(NOW), usage)
    result = await svc.search("local", "mer Rouge")  # French query, English headlines
    assert result.semantic is True
    found = {h.document.id: h for h in result.hits}
    assert set(found) == {"story:1", "post:osint/9"}
    assert found["post:osint/9"].document.unverified is True
    assert found["post:osint/9"].match is Match.SEMANTIC
    assert [r.purpose for r in usage.records] == ["embed"]
    await svc.search("local", "Hodeidah port")
    assert meaning.batches[1] == ["Hodeidah port"]  # documents came from the cache


async def test_failures_are_reported_not_raised() -> None:
    svc = SearchService(
        Stories(fail=True),
        Posts(),
        Meaning(error=ProviderUnavailableError("e", "timeout")),
        FakeWallClock(NOW),
    )
    result = await svc.search("local", "Hodeidah")
    assert result.semantic is False
    assert result.note == "news unavailable; semantic search failed: [e] timeout"
    assert [h.document.id for h in result.hits] == ["post:osint/9"]


async def test_the_search_tool() -> None:
    svc = SearchService(Stories(), Posts(), Meaning(on=False), FakeWallClock(NOW))
    box = Toolbox(finance=None, analysis=None, news=None, events=None, aviation=None, search=svc)  # type: ignore[arg-type]
    out = await box.tools["search"].run({"query": "Hodeidah"}, ToolContext("local"))
    assert out.data["hits"][0]["source"] == "Telegram @osint"
    assert out.data["hits"][0]["unverified"] is True
    assert out.sources == ("Telegram @osint",)
    with pytest.raises(ToolError):
        await box.tools["search"].run({"query": " "}, ToolContext("local"))
    empty = Toolbox(finance=None, analysis=None, news=None, events=None, aviation=None)  # type: ignore[arg-type]
    with pytest.raises(ToolError):
        await empty.tools["search"].run({"query": "x"}, ToolContext("local"))


class Recorder:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {
            "data": [{"embedding": [0.1, 0.2]} for _ in kwargs["input"]],
            "usage": {"prompt_tokens": 7},
        }


async def test_the_litellm_embedder_uses_the_owner_settings() -> None:
    config = LlmConfig(
        model="ollama/mistral",
        api_base="http://ollama:11434",
        embedding_model="ollama/nomic-embed-text",
    )

    async def resolve(owner: str) -> LlmConfig | None:
        return config

    recorder = Recorder()
    embedder = LiteLLMEmbedder(resolve, timeout_s=30, embed=recorder)
    assert await embedder.available("local") is True
    out = await embedder.embed("local", ["a"] * 70)
    assert out is not None
    assert len(out.vectors) == 70
    assert [len(c["input"]) for c in recorder.calls] == [64, 6]  # batched
    assert recorder.calls[0]["api_base"] == "http://ollama:11434"
    assert (out.input_tokens, out.cost_usd) == (14, 0.0)

    class BadRequestError(Exception):
        pass

    with pytest.raises(ProviderResponseError):
        await LiteLLMEmbedder(resolve, timeout_s=30, embed=Recorder(BadRequestError("no"))).embed(
            "local", ["a"]
        )


async def test_no_embedding_model_means_none() -> None:
    async def resolve(owner: str) -> LlmConfig | None:
        return LlmConfig(model="anthropic/claude-sonnet-5")

    embedder = LiteLLMEmbedder(resolve, timeout_s=30, embed=Recorder())
    assert await embedder.available("local") is False
    assert await embedder.embed("local", ["a"]) is None
