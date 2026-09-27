from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from argus.api.deps import (
    AssistantDep,
    AssistantSettingsDep,
    NotesDep,
    OwnerDep,
    PredictionAnalystDep,
    SearchDep,
)
from argus.domain.llm import ChatMessage, CompletionQuery, ModelUsage, Role
from argus.domain.search import Hit
from argus.providers.errors import ProviderError
from argus.services.assistant.agent import Answer, Context
from argus.services.assistant.settings import SettingsUpdate, SettingsView

router = APIRouter(prefix="/assistant", tags=["assistant"])


class SettingsOut(BaseModel):
    model: str | None
    api_base: str | None
    key_set: bool
    key_hint: str | None = Field(description="Last characters only; the key is never returned")
    source: Literal["app", "environment", "none"]
    fallbacks: list[str]
    available: bool
    embedding_model: str | None = Field(description="Semantic search; None = keywords only")


class SettingsIn(BaseModel):
    model: str | None = Field(default=None, max_length=200)
    api_base: str | None = Field(default=None, max_length=500, pattern=r"^https?://\S+$")
    api_key: str | None = Field(
        default=None, max_length=500, description="Omit to keep the stored key; empty to remove it"
    )
    embedding_model: str | None = Field(default=None, max_length=200)


class TestOut(BaseModel):
    ok: bool
    model: str | None
    elapsed_s: float | None
    error: str | None


class ContextIn(BaseModel):
    kind: str = Field(max_length=60)
    title: str = Field(max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    details: dict[str, str] = Field(default_factory=dict, max_length=20)


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: ContextIn | None = None
    history: list[TurnIn] = Field(default_factory=list, max_length=12)


class StepOut(BaseModel):
    tool: str
    args: dict[str, object]
    ok: bool
    summary: str


class AnswerOut(BaseModel):
    text: str
    conclusive: bool
    steps: list[StepOut]
    sources: list[str] = Field(description="Tools actually read, not what the model claims")
    ungrounded: list[str] = Field(description="Figures in the text that no tool returned")
    provider: str
    model: str
    elapsed_s: float
    structured: bool
    focus: FocusOut | None = Field(description="From the tools called, never from the model")
    stance: str | None = None


class FocusOut(BaseModel):
    lat: float | None
    lon: float | None
    zoom: float | None
    country: str | None
    layers: list[str]


class PredictionIn(BaseModel):
    market_id: str = Field(min_length=1, max_length=200)
    tag: str = Field(default="geopolitics", pattern=r"^[a-z0-9-]+$")


class PredictionReadingOut(BaseModel):
    market_id: str
    question: str
    stance: Literal["leans_yes", "leans_no", "no_conclusion"]
    answer: AnswerOut


class UsageOut(BaseModel):
    days: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float = Field(description="LiteLLM's estimate; local models count as 0")
    calls_without_cost: int
    by_model: list[ModelUsage]


class SearchOut(BaseModel):
    query: str
    hits: list[Hit]
    semantic: bool = Field(description="False: keywords only (no embedding model configured)")
    searched: int
    note: str | None


class NoteOut(BaseModel):
    text: str
    facts: list[str]
    written_by: str
    generated_at: str
    rejected: list[str]


def _settings_out(view: SettingsView) -> SettingsOut:
    return SettingsOut(
        model=view.model,
        api_base=view.api_base,
        key_set=view.key_set,
        key_hint=view.key_hint,
        source=view.source.value,
        fallbacks=list(view.fallbacks),
        available=view.model is not None,
        embedding_model=view.embedding_model,
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings(settings: AssistantSettingsDep, owner: OwnerDep) -> SettingsOut:
    return _settings_out(await settings.view(owner))


@router.put("/settings", response_model=SettingsOut)
async def put_settings(
    body: SettingsIn, settings: AssistantSettingsDep, owner: OwnerDep
) -> SettingsOut:
    """Choose the model. The key is stored server side and never sent back."""
    view = await settings.save(
        owner,
        SettingsUpdate(
            model=body.model,
            api_base=body.api_base,
            api_key=body.api_key,
            embedding_model=body.embedding_model,
        ),
    )
    return _settings_out(view)


@router.post("/settings/test", response_model=TestOut)
async def test_settings(assistant: AssistantDep, owner: OwnerDep) -> TestOut:
    """A one-word completion, to check the model and key before relying on them."""
    import time

    started = time.monotonic()
    try:
        c = await assistant.complete(
            owner,
            CompletionQuery(
                system="Reply with the single word: ok",
                messages=(ChatMessage(role=Role.USER, content="ping"),),
                max_tokens=16,
            ),
            purpose="test",
        )
    except ProviderError as exc:
        return TestOut(ok=False, model=None, elapsed_s=None, error=str(exc))
    return TestOut(
        ok=True, model=c.model, elapsed_s=round(time.monotonic() - started, 1), error=None
    )


@router.get("/models", response_model=list[str])
async def local_models(
    settings: AssistantSettingsDep,
    api_base: Annotated[str, Query(pattern=r"^https?://\S+$", max_length=500)],
) -> list[str]:
    """Models pulled on an Ollama server, to pick from."""
    return await settings.local_models(api_base)


@router.post("/ask", response_model=AnswerOut)
async def ask(body: AskIn, assistant: AssistantDep, owner: OwnerDep) -> AnswerOut:
    """Answer from Argus' own data: the steps, the sources read, and unbacked figures."""
    context = (
        Context(
            body.context.kind,
            body.context.title,
            body.context.lat,
            body.context.lon,
            body.context.details,
        )
        if body.context
        else None
    )
    history = [ChatMessage(role=Role(t.role), content=t.content) for t in body.history]
    a = await assistant.ask(owner, body.question, context=context, history=history)
    return _answer_out(a)


def _answer_out(a: Answer) -> AnswerOut:
    return AnswerOut(
        text=a.text,
        conclusive=a.conclusive,
        steps=[StepOut(tool=s.tool, args=s.args, ok=s.ok, summary=s.summary) for s in a.steps],
        sources=a.sources,
        ungrounded=a.ungrounded,
        provider=a.provider,
        model=a.model,
        elapsed_s=a.elapsed_s,
        structured=a.structured,
        stance=a.stance,
        focus=FocusOut(
            lat=a.focus.lat, lon=a.focus.lon, zoom=a.focus.zoom,
            country=a.focus.country, layers=list(a.focus.layers),
        )
        if a.focus
        else None,
    )  # fmt: skip


@router.post("/analyse/prediction", response_model=PredictionReadingOut)
async def analyse_prediction(
    body: PredictionIn, analyst: PredictionAnalystDep, owner: OwnerDep
) -> PredictionReadingOut:
    """Whether Argus' own data leans the way a prediction market prices — or not at all."""
    reading = await analyst.read(owner, body.market_id, body.tag)
    return PredictionReadingOut(
        market_id=reading.market.id,
        question=reading.market.question,
        stance=reading.stance,
        answer=_answer_out(reading.answer),
    )


@router.get("/usage", response_model=UsageOut)
async def usage(
    assistant: AssistantDep, owner: OwnerDep, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> UsageOut:
    """Model calls, tokens and estimated cost over the last `days`."""
    rows = await assistant.usage(owner, days)
    return UsageOut(
        days=days,
        calls=sum(r.calls for r in rows),
        input_tokens=sum(r.input_tokens for r in rows),
        output_tokens=sum(r.output_tokens for r in rows),
        cost_usd=round(sum(r.cost_usd for r in rows), 6),
        calls_without_cost=sum(r.calls_without_cost for r in rows),
        by_model=rows,
    )


@router.get("/notes/markets", response_model=NoteOut)
async def market_note(notes: NotesDep, owner: OwnerDep) -> NoteOut:
    """Figures computed by Argus; the model writes the sentence, or a template does."""
    n = await notes.market(owner)
    return NoteOut(
        text=n.text,
        facts=n.facts,
        written_by=n.written_by,
        generated_at=n.generated_at.isoformat(),
        rejected=n.rejected,
    )


@router.get("/search", response_model=SearchOut)
async def search(
    service: SearchDep,
    owner: OwnerDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    hours: Annotated[int, Query(ge=1, le=168)] = 72,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> SearchOut:
    """Hybrid search over recent news stories and the owner's Telegram channels."""
    result = await service.search(owner, q, hours=hours, limit=limit)
    return SearchOut(
        query=q,
        hits=result.hits,
        semantic=result.semantic,
        searched=result.corpus,
        note=result.note,
    )
