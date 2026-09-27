"""Language models as a capability: one port, several providers tried in order."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(DomainModel):
    role: Role
    content: str = Field(max_length=20_000)


class CompletionQuery(DomainModel):
    system: str
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    max_tokens: int = Field(default=700, ge=16, le=4000)
    temperature: float = Field(default=0.2, ge=0, le=1)
    json_mode: bool = Field(default=False, description="Ask for a single JSON object")


class Completion(DomainModel):
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = Field(
        default=None, description="LiteLLM's estimate from public prices; 0 for local models"
    )


class CompletionRequest(DomainModel):
    """A completion on behalf of an owner, whose model settings apply."""

    owner: str
    query: CompletionQuery


class LlmConfig(DomainModel):
    """Which model to call and how. Built on the server; never sent to a browser."""

    model: str = Field(min_length=3, max_length=200, pattern=r"^[\w.\-:/@]+$")
    api_key: str | None = None
    api_base: str | None = Field(default=None, pattern=r"^https?://\S+$")
    # Same key and base URL as the chat model (e.g. ollama/nomic-embed-text).
    embedding_model: str | None = Field(
        default=None, min_length=3, max_length=200, pattern=r"^[\w.\-:/@]+$"
    )


class StoredLlmSettings(DomainModel):
    model: str | None
    api_key: str | None
    api_base: str | None
    embedding_model: str | None = None


class LlmSettingsRepository(Protocol):
    async def get(self, owner: str) -> StoredLlmSettings | None: ...

    async def save(self, owner: str, settings: StoredLlmSettings) -> None: ...


LLM_COMPLETION: Capability[CompletionRequest, Completion] = Capability(
    "llm.completion", "Text completion from the chat model the owner configured."
)


class UsageRecord(DomainModel):
    owner: str
    at: datetime
    purpose: str = Field(description="ask, note, test, analysis")
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None


class ModelUsage(DomainModel):
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    calls_without_cost: int = Field(description="Calls whose price LiteLLM does not know")


class UsageRepository(Protocol):
    async def add(self, record: UsageRecord) -> None: ...

    async def summary(self, owner: str, since: datetime) -> list[ModelUsage]: ...
