import json
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.llm.litellm import LiteLLMFetcher, NotConfiguredError, parse_json_object
from argus.domain.llm import (
    ChatMessage,
    CompletionQuery,
    CompletionRequest,
    LlmConfig,
    Role,
)
from argus.providers.errors import (
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)

FIXTURE = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "litellm_ollama_reply.json").read_text()
)
QUERY = CompletionQuery(
    system="sys", messages=(ChatMessage(role=Role.USER, content="hi"),), json_mode=True
)
REQUEST = CompletionRequest(owner="local", query=QUERY)


class Recorder:
    def __init__(self, reply: Any = FIXTURE, error: Exception | None = None) -> None:
        self.reply, self.error = reply, error
        self.kwargs: dict[str, Any] = {}

    async def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.reply


def fetcher(complete: Recorder, config: LlmConfig | None) -> LiteLLMFetcher:
    async def resolve(owner: str) -> LlmConfig | None:
        assert owner == "local"
        return config

    return LiteLLMFetcher(resolve, timeout_s=30, complete=complete)


async def test_a_recorded_ollama_reply_through_litellm() -> None:
    complete = Recorder()
    config = LlmConfig(model="ollama/mistral", api_base="http://localhost:11434")
    c = await fetcher(complete, config).fetch(REQUEST)
    assert c.text == '{"answer": "ok", "conclusive": true}'
    assert (c.model, c.input_tokens, c.output_tokens) == ("ollama/mistral", 35, 13)
    assert complete.kwargs["model"] == "ollama/mistral"
    assert complete.kwargs["api_base"] == "http://localhost:11434"
    assert complete.kwargs["response_format"] == {"type": "json_object"}
    assert complete.kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert "api_key" not in complete.kwargs


async def test_the_key_is_passed_but_never_leaks_in_errors() -> None:
    class AuthenticationError(Exception):
        pass

    complete = Recorder(error=AuthenticationError("invalid x-api-key sk-secret-1234"))
    f = fetcher(complete, LlmConfig(model="anthropic/claude-sonnet-5", api_key="sk-secret-1234"))
    with pytest.raises(ProviderResponseError) as info:
        await f.fetch(REQUEST)
    assert complete.kwargs["api_key"] == "sk-secret-1234"
    assert "sk-secret-1234" not in str(info.value)
    assert "AuthenticationError" in str(info.value)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("RateLimitError", ProviderRateLimitedError),
        ("Timeout", ProviderUnavailableError),
        ("APIConnectionError", ProviderUnavailableError),
        ("BadRequestError", ProviderResponseError),
    ],
)
async def test_litellm_errors_map_onto_the_provider_hierarchy(
    name: str, expected: type[Exception]
) -> None:
    error = type(name, (Exception,), {})("boom")
    with pytest.raises(expected):
        await fetcher(Recorder(error=error), LlmConfig(model="openai/x")).fetch(REQUEST)


async def test_without_a_model_nothing_is_called() -> None:
    complete = Recorder()
    with pytest.raises(NotConfiguredError):
        await fetcher(complete, None).fetch(REQUEST)
    assert complete.kwargs == {}


@pytest.mark.parametrize("reply", [{"choices": []}, {"choices": [{"message": {"content": " "}}]}])
async def test_empty_replies_are_errors(reply: Any) -> None:
    with pytest.raises(ProviderResponseError):
        await fetcher(Recorder(reply), LlmConfig(model="openai/x")).fetch(REQUEST)


def test_json_is_found_inside_prose_and_fences() -> None:
    assert parse_json_object('Sure!\n```json\n{"tool": "news", "args": {"q": "{x}"}}\n```') == {
        "tool": "news",
        "args": {"q": "{x}"},
    }
    assert parse_json_object("no json here") is None
    assert parse_json_object('{"broken": } then {"ok": 1}') == {"ok": 1}


async def test_the_cost_estimate_travels_with_the_completion() -> None:
    async def resolve(owner: str) -> LlmConfig | None:
        return LlmConfig(model="anthropic/claude-sonnet-5")

    fetcher = LiteLLMFetcher(resolve, timeout_s=30, complete=Recorder(), cost=lambda r: 0.0042)
    assert (await fetcher.fetch(REQUEST)).cost_usd == 0.0042
    unknown = LiteLLMFetcher(resolve, timeout_s=30, complete=Recorder())
    assert (await unknown.fetch(REQUEST)).cost_usd is None


def test_litellm_prices_known_models_offline() -> None:
    from argus.adapters.llm.litellm import litellm_cost

    assert litellm_cost(object()) is None  # not a response: unknown, not an error
