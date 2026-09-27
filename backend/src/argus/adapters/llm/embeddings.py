"""Embeddings through LiteLLM (``aembedding``), with the owner's key and base URL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from argus.adapters.llm.litellm import Resolver, _translate
from argus.providers.errors import ProviderResponseError

EmbedFn = Callable[..., Awaitable[Any]]
BATCH = 64


@dataclass(frozen=True, slots=True)
class Embedded:
    vectors: list[list[float]]
    model: str
    input_tokens: int | None
    cost_usd: float | None


def litellm_embed() -> EmbedFn:
    import litellm

    return cast("EmbedFn", litellm.aembedding)


class LiteLLMEmbedder:
    def __init__(
        self, resolve: Resolver, *, timeout_s: float, embed: EmbedFn | None = None
    ) -> None:
        self._resolve = resolve
        self._timeout = timeout_s
        self._embed = embed

    async def available(self, owner: str) -> bool:
        config = await self._resolve(owner)
        return bool(config and config.embedding_model)

    async def embed(self, owner: str, texts: Sequence[str]) -> Embedded | None:
        """None when no embedding model is configured for this owner."""
        config = await self._resolve(owner)
        if config is None or not config.embedding_model:
            return None
        embed = self._embed or litellm_embed()
        vectors: list[list[float]] = []
        tokens = 0
        for start in range(0, len(texts), BATCH):
            kwargs: dict[str, Any] = {
                "model": config.embedding_model,
                "input": list(texts[start : start + BATCH]),
                "timeout": self._timeout,
            }
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.api_base:
                kwargs["api_base"] = config.api_base
            try:
                response = await embed(**kwargs)
            except Exception as exc:
                raise _translate("embeddings", exc, config.api_key) from exc
            raw = response.model_dump() if hasattr(response, "model_dump") else response
            try:
                vectors += [list(map(float, item["embedding"])) for item in raw["data"]]
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError("embeddings", "unexpected embedding payload") from exc
            tokens += int((raw.get("usage") or {}).get("prompt_tokens") or 0)
        if len(vectors) != len(texts):
            raise ProviderResponseError("embeddings", "one vector per text expected")
        local = config.embedding_model.startswith("ollama/")
        return Embedded(vectors, config.embedding_model, tokens or None, 0.0 if local else None)
