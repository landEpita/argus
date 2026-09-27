"""
Grounded notes: the figures are computed here, the model only writes prose.

If the model's text contains a number that is not among the facts, it is
discarded and a plain sentence built from the facts is used instead — the
note says which one the reader is seeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from argus.domain.grounding import ungrounded
from argus.domain.llm import ChatMessage, CompletionQuery, Role
from argus.infra.clock import WallClock
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.services.assistant.agent import AssistantService
from argus.services.finance import FinanceService

MOVERS = 3

NOTE_SYSTEM = """You write one short market note (at most 2 sentences) for an analyst.
Use ONLY the facts given, with their exact figures. Do not add numbers, forecasts or
explanations. Never claim that one fact caused another; you may say they coincide.
Reply with the note only."""


@dataclass(frozen=True, slots=True)
class Note:
    text: str
    facts: list[str]
    written_by: str  # the model, or "template" when the model's text was not grounded
    generated_at: datetime
    rejected: list[str]  # figures the model invented, when its text was discarded


def _pct(value: float) -> str:
    return f"{value:+.2f} %".replace("-", "\N{MINUS SIGN}")


async def market_facts(finance: FinanceService) -> list[str]:
    facts: list[str] = []
    board = await finance.quotes()
    moved = sorted(
        (q for q in board.items if q.change_pct is not None),
        key=lambda q: abs(q.change_pct or 0),
        reverse=True,
    )[:MOVERS]
    facts += [f"{q.instrument.name} {_pct(q.change_pct or 0)} on the session" for q in moved]
    try:
        choke = sorted(
            (c for c in await finance.chokepoints() if c.change_vs_last_year_pct is not None),
            key=lambda c: c.change_vs_last_year_pct or 0,
        )
        facts += [
            f"{c.name} traffic {_pct(c.change_vs_last_year_pct or 0)} vs the same week last year"
            for c in choke[:2]
            if (c.change_vs_last_year_pct or 0) <= -30
        ]
    except (NoProviderError, AllProvidersFailedError):
        pass
    return facts


class NotesService:
    def __init__(
        self, assistant: AssistantService, finance: FinanceService, clock: WallClock
    ) -> None:
        self._assistant = assistant
        self._finance = finance
        self._clock = clock

    async def market(self, owner: str) -> Note:
        facts = await market_facts(self._finance)
        now = self._clock.utcnow()
        template = "; ".join(facts) + "." if facts else "No market data right now."
        if not facts or not await self._assistant.available(owner):
            return Note(template, facts, "template", now, [])
        completion = await self._assistant.complete(
            owner,
            CompletionQuery(
                system=NOTE_SYSTEM,
                messages=(ChatMessage(role=Role.USER, content="Facts:\n- " + "\n- ".join(facts)),),
                max_tokens=160,
            ),
            purpose="note",
        )
        text = completion.text.strip()
        invented = ungrounded(text, facts)
        if invented:
            return Note(template, facts, "template", now, invented)
        return Note(text, facts, completion.model, now, [])
