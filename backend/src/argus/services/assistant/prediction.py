"""
Grounded reading of a prediction market: does Argus' data lean one way?

The market's price is the crowd's; Argus only says whether its own feeds
point the same way, the other way, or do not settle it — the last one being
a normal and frequent outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from argus.domain.errors import NotFoundError
from argus.domain.markets import PredictionMarket
from argus.services.assistant.agent import Answer, AssistantService
from argus.services.finance import FinanceService

STANCES = ("leans_yes", "leans_no", "no_conclusion")


@dataclass(frozen=True, slots=True)
class Reading:
    market: PredictionMarket
    answer: Answer
    stance: str


def question_for(m: PredictionMarket) -> str:
    odds = ", ".join(f"{o.label} {o.probability * 100:.0f} %" for o in m.outcomes)
    closes = f" It closes on {m.end_date.date().isoformat()}." if m.end_date else ""
    return (
        f"A prediction market asks: “{m.question}”. Traders currently price: {odds}.{closes} "
        "Using only Argus data, does the evidence lean towards yes, towards no, or not settle "
        "it? Name the evidence. Do not repeat the market price as evidence."
    )


class PredictionAnalyst:
    def __init__(self, assistant: AssistantService, finance: FinanceService) -> None:
        self._assistant = assistant
        self._finance = finance

    async def read(self, owner: str, market_id: str, tag: str = "geopolitics") -> Reading:
        markets = await self._finance.prediction(tag, 100)
        market = next((m for m in markets if m.id == market_id), None)
        if market is None:
            raise NotFoundError("prediction market", market_id)
        answer = await self._assistant.ask(owner, question_for(market), stances=STANCES)
        return Reading(market, answer, answer.stance or "no_conclusion")
