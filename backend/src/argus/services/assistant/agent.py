"""
The assistant's answer loop (a small tool planner).

The model reads Argus' data through tools, with a JSON protocol that works
with any chat model LiteLLM reaches — local or hosted, with or without native
tool calling:

    {"tool": "<name>", "args": {...}}          read data (up to MAX_STEPS times)
    {"answer": "<text>", "conclusive": bool}   finish

Honesty is enforced outside the model where it can be: sources are the tools
actually called, and every figure in the answer is checked against what the
tools returned (``grounding.ungrounded``). Saying "I cannot conclude" is a
normal outcome, not an error.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from argus.adapters.llm.litellm import parse_json_object
from argus.domain.grounding import ungrounded
from argus.domain.llm import (
    LLM_COMPLETION,
    ChatMessage,
    Completion,
    CompletionQuery,
    CompletionRequest,
    ModelUsage,
    Role,
    UsageRecord,
    UsageRepository,
)
from argus.infra.clock import WallClock
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.providers.registry import ProviderRegistry
from argus.services.assistant.focus import MapFocus, focus_from
from argus.services.assistant.settings import AssistantSettingsService
from argus.services.assistant.tools import ToolContext, ToolError, ToolSet

MAX_STEPS = 4
RESULT_CHARS = 6000
HISTORY_TURNS = 6

SYSTEM = """You are Argus, the analyst assistant of an OSINT and markets console.
You answer ONLY from data returned by the tools below; you know nothing else about
current events.

Reply with exactly ONE JSON object, nothing else:
  {{"tool": "<name>", "args": {{...}}}}              to read data (at most {steps} calls), or
  {{"answer": "<text>", "conclusive": true|false}}   when you are done.

Rules for the answer:
- Every number must come from a tool result. Never estimate or round beyond the data.
- Press-coded events (GDELT, "conflict") and state media are unverified: say so.
- If the data does not settle the question, say what is missing and set
  "conclusive": false. That is a normal, useful answer.
- Never claim causation from coincidence: write "coincides with", not "because of".
- 2 to 5 short sentences, in the language of the question.

Tools:
{catalogue}

Now: {now} UTC."""


def _nudge_message(kind: str, text: str, evidence: list[str]) -> str:
    if kind == "no_data":
        return (
            "You have not read any data yet. Call the tool that holds the answer first; "
            "answer without data only if no tool covers the question (then conclusive: false)."
        )
    return (
        f"These figures are not in the tool results: {', '.join(ungrounded(text, evidence))}. "
        "Rewrite the answer using only figures from the results, or none."
    )


@dataclass(frozen=True, slots=True)
class Context:
    """What the user is looking at when they ask (an object on the map, an asset…)."""

    kind: str
    title: str
    lat: float | None = None
    lon: float | None = None
    details: dict[str, str] = field(default_factory=dict)

    def describe(self) -> str:
        where = (
            f" at lat {self.lat:.2f}, lon {self.lon:.2f}"
            if self.lat is not None and self.lon is not None
            else ""
        )
        extra = "; ".join(f"{k}: {v}" for k, v in list(self.details.items())[:12])
        return f"The user is looking at {self.kind} “{self.title}”{where}. {extra}".strip()


@dataclass(frozen=True, slots=True)
class Step:
    tool: str
    args: dict[str, Any]
    ok: bool
    summary: str


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    conclusive: bool
    steps: list[Step]
    sources: list[str]
    ungrounded: list[str]
    provider: str
    model: str
    elapsed_s: float
    structured: bool = True
    focus: MapFocus | None = None
    stance: str | None = None


def _summary(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("count",):
            if key in data:
                return f"{data[key]} items"
        lists = [v for v in data.values() if isinstance(v, list)]
        if lists:
            return f"{len(lists[0])} items"
        return f"{len(data)} fields"
    return "ok"


class AssistantService:
    def __init__(
        self,
        registry: ProviderRegistry,
        toolbox: ToolSet,
        settings: AssistantSettingsService,
        clock: WallClock,
        usage: UsageRepository | None = None,
    ) -> None:
        self._usage = usage
        self._registry = registry
        self._tools = toolbox
        self._settings = settings
        self._clock = clock

    @property
    def tools(self) -> ToolSet:
        return self._tools

    async def available(self, owner: str) -> bool:
        return await self._settings.config(owner) is not None

    async def complete(
        self, owner: str, query: CompletionQuery, *, purpose: str = "ask"
    ) -> Completion:
        """One completion with the owner's model; 503 capability_disabled when none is set."""
        if not await self.available(owner):
            raise NoProviderError(LLM_COMPLETION.name)
        completion = await self._registry.fetch(
            LLM_COMPLETION, CompletionRequest(owner=owner, query=query)
        )
        if self._usage is not None:
            await self._usage.add(
                UsageRecord(
                    owner=owner,
                    at=self._clock.utcnow(),
                    purpose=purpose,
                    provider=completion.provider,
                    model=completion.model,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    cost_usd=completion.cost_usd,
                )
            )
        return completion

    async def usage(self, owner: str, days: int) -> list[ModelUsage]:
        if self._usage is None:
            return []
        return await self._usage.summary(owner, self._clock.utcnow() - timedelta(days=days))

    async def ask(
        self,
        owner: str,
        question: str,
        *,
        context: Context | None = None,
        history: Sequence[ChatMessage] = (),
        stances: Sequence[str] = (),
    ) -> Answer:
        """`stances`, when given, lets the model add one of them as "stance" in its answer."""
        started = time.monotonic()
        system = SYSTEM.format(
            steps=MAX_STEPS,
            catalogue=self._tools.catalogue(),
            now=self._clock.utcnow().isoformat(timespec="minutes"),
        )
        prompt = f"{context.describe()}\n\n{question}" if context else question
        if stances:
            prompt += (
                '\n\nIn your answer object, add "stance": one of '
                + ", ".join(f'"{s}"' for s in stances)
                + "."
            )
        messages = [*history[-HISTORY_TURNS:], ChatMessage(role=Role.USER, content=prompt)]
        steps: list[Step] = []
        sources: list[str] = []
        evidence: list[str] = [prompt]
        retried = False
        nudged: set[str] = set()
        last: Completion | None = None

        # Room for every tool call, two corrections and the final answer.
        for _ in range(MAX_STEPS + 4):
            last = await self.complete(
                owner, CompletionQuery(system=system, messages=tuple(messages), json_mode=True)
            )
            reply = parse_json_object(last.text)
            if reply is None or not ({"answer", "tool"} & reply.keys()):
                if retried:
                    return self._finish(
                        last.text, False, steps, sources, evidence, last, started, structured=False
                    )
                retried = True
                messages += [
                    ChatMessage(role=Role.ASSISTANT, content=last.text[:2000]),
                    ChatMessage(
                        role=Role.USER, content="Reply with ONE JSON object following the protocol."
                    ),
                ]
                continue
            if "answer" in reply:
                text = str(reply["answer"]).strip()
                nudge = self._nudge(text, steps, evidence, nudged)
                if nudge:
                    nudged.add(nudge)
                    messages += [
                        ChatMessage(role=Role.ASSISTANT, content=last.text[:2000]),
                        ChatMessage(role=Role.USER, content=_nudge_message(nudge, text, evidence)),
                    ]
                    continue
                stance = reply.get("stance")
                return self._finish(
                    text,
                    bool(reply.get("conclusive", False)),
                    steps,
                    sources,
                    evidence,
                    last,
                    started,
                    stance=stance if isinstance(stance, str) and stance in stances else None,
                )

            name = str(reply.get("tool"))
            raw_args = reply.get("args")
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            messages.append(
                ChatMessage(role=Role.ASSISTANT, content=json.dumps({"tool": name, "args": args}))
            )
            if len(steps) >= MAX_STEPS:
                messages.append(
                    ChatMessage(role=Role.USER, content="No more tool calls: give your answer now.")
                )
                continue
            result = await self._run(name, args, steps, sources, ToolContext(owner))
            evidence.append(result)
            messages.append(
                ChatMessage(role=Role.USER, content=f"Result of {name}:\n{result}\n\nContinue.")
            )

        if last is None:  # pragma: no cover - the loop always runs at least once
            raise RuntimeError("no completion")
        return self._finish(
            "I could not reach an answer within the allowed steps.",
            False, steps, sources, evidence, last, started,
        )  # fmt: skip

    @staticmethod
    def _nudge(text: str, steps: list[Step], evidence: list[str], done: set[str]) -> str | None:
        """One chance each to read data first, and to drop figures the data lacks."""
        if not steps and "no_data" not in done:
            return "no_data"
        if steps and "ungrounded" not in done and ungrounded(text, evidence):
            return "ungrounded"
        return None

    async def _run(
        self,
        name: str,
        args: dict[str, Any],
        steps: list[Step],
        sources: list[str],
        ctx: ToolContext,
    ) -> str:
        tool = self._tools.tools.get(name)
        if tool is None:
            steps.append(Step(name, args, False, "unknown tool"))
            return json.dumps(
                {"error": f"unknown tool {name}; use one of {list(self._tools.tools)}"}
            )
        try:
            output = await tool.run(args, ctx)
        except ToolError as exc:
            steps.append(Step(name, args, False, str(exc)))
            return json.dumps({"error": str(exc)})
        except (NoProviderError, AllProvidersFailedError) as exc:
            steps.append(Step(name, args, False, "source unavailable"))
            return json.dumps({"error": f"source unavailable: {exc}"})
        steps.append(Step(name, args, True, _summary(output.data)))
        for s in output.sources:
            if s not in sources:
                sources.append(s)
        return json.dumps(output.data, default=str, ensure_ascii=False)[:RESULT_CHARS]

    def _finish(
        self,
        text: str,
        conclusive: bool,
        steps: list[Step],
        sources: list[str],
        evidence: list[str],
        completion: Completion,
        started: float,
        *,
        structured: bool = True,
        stance: str | None = None,
    ) -> Answer:
        conclusive = conclusive and bool(steps)
        return Answer(
            text=text,
            conclusive=conclusive,
            steps=steps,
            sources=sources,
            ungrounded=ungrounded(text, evidence),
            provider=completion.provider,
            model=completion.model,
            elapsed_s=round(time.monotonic() - started, 1),
            structured=structured,
            focus=focus_from(steps),
            # A lean needs data behind it; otherwise the honest stance is none.
            stance=stance if conclusive and not ungrounded(text, evidence) else None,
        )
