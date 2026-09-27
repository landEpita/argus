from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from argus.domain.llm import LLM_COMPLETION, Completion, CompletionRequest, LlmConfig
from argus.providers.base import Fetcher
from argus.providers.errors import NoProviderError
from argus.providers.registry import ProviderRegistry
from argus.services.assistant.agent import MAX_STEPS, AssistantService, Context
from argus.services.assistant.settings import AssistantSettingsService
from argus.services.assistant.tools import Tool, ToolContext, ToolError, ToolOutput
from tests.fakes import FakeWallClock
from tests.unit.assistant.test_settings import MemoryRepo

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


class ScriptedModel(Fetcher[CompletionRequest, Completion]):
    provider_name = "llm"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.requests: list[CompletionRequest] = []

    async def extract(self, params: Mapping[str, str]) -> Any:
        return None

    def transform(self, query: CompletionRequest, raw: Any) -> Completion:
        self.requests.append(query)
        text = self.replies.pop(0) if self.replies else '{"answer": "done", "conclusive": false}'
        return Completion(text=text, provider="llm", model="ollama/mistral")


class Tools:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

        async def quotes(args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
            self.calls.append(dict(args))
            return ToolOutput(
                {"quotes": [{"name": "Brent", "price": 97.44, "change_pct": -8.59}]},
                ("Yahoo Finance (delayed)",),
            )

        async def broken(args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
            raise ToolError("symbol must be a Yahoo symbol")

        async def disabled(args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
            raise NoProviderError("events.fires")

        self._tools = {
            "quotes": Tool("quotes", "prices", {}, quotes),
            "asset": Tool("asset", "one asset", {"symbol": "text"}, broken),
            "fires": Tool("fires", "fires", {}, disabled),
        }

    @property
    def tools(self) -> Mapping[str, Tool]:
        return self._tools

    def catalogue(self) -> str:
        return "- quotes(): prices\n- asset(symbol)\n- fires()"


def service(model: ScriptedModel, *, configured: bool = True) -> tuple[AssistantService, Tools]:
    registry = ProviderRegistry()
    registry.register(LLM_COMPLETION, model)
    settings = AssistantSettingsService(
        MemoryRepo(), LlmConfig(model="ollama/mistral") if configured else None
    )
    tools = Tools()
    return AssistantService(registry, tools, settings, FakeWallClock(NOW)), tools


async def test_reads_data_then_answers_with_the_sources_it_read() -> None:
    model = ScriptedModel(
        '{"tool": "quotes", "args": {}}',
        '{"answer": "Brent is down 8.59 % at 97.44.", "conclusive": true}',
    )
    svc, _ = service(model)
    a = await svc.ask("local", "How is oil doing?")
    assert a.text == "Brent is down 8.59 % at 97.44."
    assert a.conclusive is True
    assert [(s.tool, s.ok, s.summary) for s in a.steps] == [("quotes", True, "1 items")]
    assert a.sources == ["Yahoo Finance (delayed)"]
    assert a.ungrounded == []
    assert (a.provider, a.model, a.structured) == ("llm", "ollama/mistral", True)
    # The tool result went back to the model, with the system prompt's tool list.
    second = model.requests[1].query
    assert "Result of quotes" in second.messages[-1].content
    assert "- quotes(): prices" in second.system
    assert second.json_mode is True


async def test_invented_figures_are_sent_back_once_then_flagged() -> None:
    invented = '{"answer": "Brent fell 12.5 % to 91.", "conclusive": true}'
    model = ScriptedModel('{"tool": "quotes"}', invented, invented)
    a = await service(model)[0].ask("local", "oil?")
    assert "These figures are not in the tool results: 12.5, 91" in (
        model.requests[2].query.messages[-1].content
    )
    assert a.ungrounded == ["12.5", "91"]


async def test_a_corrected_answer_passes() -> None:
    model = ScriptedModel(
        '{"tool": "quotes"}',
        '{"answer": "Brent fell 12.5 %.", "conclusive": true}',
        '{"answer": "Brent fell 8.59 %.", "conclusive": true}',
    )
    a = await service(model)[0].ask("local", "oil?")
    assert (a.text, a.ungrounded, a.conclusive) == ("Brent fell 8.59 %.", [], True)


async def test_answering_without_data_is_sent_back_to_read_first() -> None:
    model = ScriptedModel(
        '{"answer": "Oil is at 83.6.", "conclusive": true}',
        '{"tool": "quotes"}',
        '{"answer": "Brent is at 97.44.", "conclusive": true}',
    )
    a = await service(model)[0].ask("local", "oil?")
    assert "You have not read any data yet" in model.requests[1].query.messages[-1].content
    assert [s.tool for s in a.steps] == ["quotes"]
    assert (a.text, a.ungrounded) == ("Brent is at 97.44.", [])


async def test_an_answer_without_data_is_never_conclusive() -> None:
    reply = '{"answer": "No tool covers the weather in Paris.", "conclusive": true}'
    a = await service(ScriptedModel(reply, reply))[0].ask("local", "Weather in Paris?")
    assert a.conclusive is False
    assert a.steps == []


async def test_tool_errors_go_back_to_the_model() -> None:
    model = ScriptedModel(
        '{"tool": "asset", "args": {"symbol": "??"}}',
        '{"tool": "nope"}',
        '{"tool": "fires"}',
        '{"answer": "Not enough data.", "conclusive": false}',
    )
    a = await service(model)[0].ask("local", "q")
    assert [(s.tool, s.ok, s.summary) for s in a.steps] == [
        ("asset", False, "symbol must be a Yahoo symbol"),
        ("nope", False, "unknown tool"),
        ("fires", False, "source unavailable"),
    ]
    assert a.sources == []
    assert "unknown tool nope" in model.requests[2].query.messages[-1].content


async def test_prose_gets_one_correction_then_is_returned_as_is() -> None:
    model = ScriptedModel("Hello there", "Still prose")
    a = await service(model)[0].ask("local", "q")
    assert (a.text, a.structured, a.conclusive) == ("Still prose", False, False)
    assert "ONE JSON object" in model.requests[1].query.messages[-1].content


async def test_tool_calls_are_capped() -> None:
    model = ScriptedModel(
        *(['{"tool": "quotes"}'] * (MAX_STEPS + 1)), '{"answer": "ok", "conclusive": true}'
    )
    svc, tools = service(model)
    a = await svc.ask("local", "q")
    assert len(tools.calls) == MAX_STEPS
    assert a.text == "ok"
    assert "No more tool calls" in model.requests[MAX_STEPS + 1].query.messages[-1].content


async def test_context_and_history_reach_the_model() -> None:
    from argus.domain.llm import ChatMessage, Role

    model = ScriptedModel('{"answer": "It is a Boeing.", "conclusive": false}')
    svc, _ = service(model)
    await svc.ask(
        "local",
        "What is it?",
        context=Context("aircraft", "SWR8LR", 46.2, 9.8, {"type": "B77W"}),
        history=[
            ChatMessage(role=Role.USER, content="earlier"),
            ChatMessage(role=Role.ASSISTANT, content="reply"),
        ],
    )
    messages = model.requests[0].query.messages
    assert [m.content for m in messages[:2]] == ["earlier", "reply"]
    assert "aircraft “SWR8LR” at lat 46.20, lon 9.80" in messages[-1].content
    assert "type: B77W" in messages[-1].content


async def test_without_a_model_the_capability_is_disabled() -> None:
    import pytest

    svc, _ = service(ScriptedModel(), configured=False)
    assert await svc.available("local") is False
    with pytest.raises(NoProviderError):
        await svc.ask("local", "q")


async def test_every_completion_is_recorded_with_its_purpose() -> None:
    from argus.domain.llm import ModelUsage, UsageRecord

    class Usage:
        def __init__(self) -> None:
            self.records: list[UsageRecord] = []

        async def add(self, record: UsageRecord) -> None:
            self.records.append(record)

        async def summary(self, owner: str, since: datetime) -> list[ModelUsage]:
            assert since == NOW - timedelta(days=7)
            return []

    usage = Usage()
    registry = ProviderRegistry()
    registry.register(
        LLM_COMPLETION, ScriptedModel('{"tool": "quotes"}', '{"answer": "ok", "conclusive": true}')
    )
    settings = AssistantSettingsService(MemoryRepo(), LlmConfig(model="ollama/mistral"))
    svc = AssistantService(registry, Tools(), settings, FakeWallClock(NOW), usage)
    await svc.ask("local", "q")
    assert [(r.owner, r.purpose, r.model) for r in usage.records] == [
        ("local", "ask", "ollama/mistral")
    ] * 2
    assert await svc.usage("local", 7) == []
    assert await service(ScriptedModel())[0].usage("local", 7) == []  # no repository: nothing
