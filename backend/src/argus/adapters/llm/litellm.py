"""
Every chat model through LiteLLM: ``ollama/mistral``, ``anthropic/claude-sonnet-5``,
``openai/…``, ``groq/…``, ``openrouter/…`` and a hundred others, with one call.

The model, key and base URL come from a resolver (the owner's saved settings,
or the environment), so changing model in the app needs no restart. LiteLLM's
errors are translated into the provider hierarchy so fallback and health work
as for any other source.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from argus.domain.llm import Completion, CompletionRequest, LlmConfig
from argus.providers.base import Fetcher
from argus.providers.errors import (
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)

# Keep LiteLLM offline at import (no model-price download) and quiet.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

CompleteFn = Callable[..., Awaitable[Any]]
CostFn = Callable[[Any], float | None]
Resolver = Callable[[str], Awaitable[LlmConfig | None]]
PARAMS = "request"


def litellm_cost(response: Any) -> float | None:
    """LiteLLM's estimate from its bundled price list; None for unknown models."""
    import litellm

    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception:  # unknown model or missing usage: the cost is simply unknown
        return None


def litellm_complete() -> CompleteFn:
    import litellm  # heavy import, deferred until a model is actually used

    litellm.suppress_debug_info = True
    litellm.telemetry = False
    return cast("CompleteFn", litellm.acompletion)


class NotConfiguredError(ProviderUnavailableError):
    """No model is configured for this owner."""


class LiteLLMFetcher(Fetcher[CompletionRequest, Completion]):
    provider_name = "llm"

    def __init__(
        self,
        resolve: Resolver,
        *,
        timeout_s: float,
        name: str = "llm",
        complete: CompleteFn | None = None,
        cost: CostFn | None = None,
    ) -> None:
        self._cost = cost
        self._resolve = resolve
        self._timeout = timeout_s
        self.provider_name = name
        self._complete = complete

    def transform_query(self, query: CompletionRequest) -> Mapping[str, str]:
        return {PARAMS: query.model_dump_json()}

    async def extract(self, params: Mapping[str, str]) -> Any:
        request = CompletionRequest.model_validate_json(params[PARAMS])
        config = await self._resolve(request.owner)
        if config is None:
            raise NotConfiguredError(self.provider_name, "no model configured")
        q = request.query
        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": q.system},
                *({"role": m.role.value, "content": m.content} for m in q.messages),
            ],
            "max_tokens": q.max_tokens,
            "temperature": q.temperature,
            "timeout": self._timeout,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.api_base:
            kwargs["api_base"] = config.api_base
        if q.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        complete = self._complete or litellm_complete()
        try:
            response = await complete(**kwargs)
        except Exception as exc:  # LiteLLM raises its own hierarchy; map it by name
            raise _translate(self.provider_name, exc, config.api_key) from exc
        raw = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        cost = self._cost or (litellm_cost if self._complete is None else None)
        raw["_cost_usd"] = cost(response) if cost else None
        return raw

    def transform(self, query: CompletionRequest, raw: Any) -> Completion:
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(self.provider_name, "no choice in reply") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderResponseError(self.provider_name, "empty reply")
        usage = raw.get("usage") or {}
        model = str(raw.get("model") or "")
        return Completion(
            text=text,
            provider=self.provider_name,
            model=model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cost_usd=raw.get("_cost_usd"),
        )


_UNAVAILABLE = {
    "Timeout",
    "APIConnectionError",
    "ServiceUnavailableError",
    "InternalServerError",
    "APIError",
}


def _translate(provider: str, exc: Exception, secret: str | None) -> Exception:
    kind = type(exc).__name__
    message = str(exc).splitlines()[0][:240] if str(exc) else kind
    if secret:
        message = message.replace(secret, "…")  # never let a key reach logs or the UI
    detail = f"{kind}: {message}"
    if kind == "RateLimitError":
        return ProviderRateLimitedError(provider, detail, None)
    if kind in _UNAVAILABLE:
        return ProviderUnavailableError(provider, detail)
    return ProviderResponseError(provider, detail)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """The first JSON object in a reply (models sometimes wrap it in prose or fences)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                    except ValueError:
                        break
                    return value if isinstance(value, dict) else None
        start = text.find("{", start + 1)
    return None
