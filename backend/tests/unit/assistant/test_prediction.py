from datetime import UTC, datetime

import pytest

from argus.domain.errors import NotFoundError
from argus.domain.markets import Outcome, PredictionMarket
from argus.services.assistant.prediction import STANCES, PredictionAnalyst, question_for
from tests.unit.assistant.test_agent import ScriptedModel, service

MARKET = PredictionMarket(
    id="m1",
    question="Shipping through Hormuz disrupted before 31 Dec?",
    event_title="Hormuz",
    outcomes=(Outcome(label="Yes", probability=0.18), Outcome(label="No", probability=0.82)),
    end_date=datetime(2026, 12, 31, tzinfo=UTC),
    url="https://polymarket.com/event/x",
    source="polymarket",
)


class Finance:
    async def prediction(self, tag: str, limit: int) -> list[PredictionMarket]:
        return [MARKET]


def test_the_question_carries_the_price_but_not_as_evidence() -> None:
    q = question_for(MARKET)
    assert "Yes 18 %, No 82 %" in q
    assert "closes on 2026-12-31" in q
    assert "Do not repeat the market price as evidence" in q


async def test_a_lean_needs_data_and_grounded_figures() -> None:
    model = ScriptedModel(
        '{"tool": "quotes"}',
        '{"answer": "Brent is down 8.59 %; nothing shows a disruption.",'
        ' "conclusive": true, "stance": "leans_no"}',
    )
    analyst = PredictionAnalyst(service(model)[0], Finance())  # type: ignore[arg-type]
    reading = await analyst.read("local", "m1")
    assert reading.stance == "leans_no"
    assert (
        'add "stance": one of "leans_yes", "leans_no", "no_conclusion"'
        in model.requests[0].query.messages[-1].content
    )


@pytest.mark.parametrize(
    "replies",
    [
        # Not conclusive: no lean, whatever the model says.
        [
            '{"tool": "quotes"}',
            '{"answer": "Unclear.", "conclusive": false, "stance": "leans_yes"}',
        ],
        # A stance outside the allowed set is dropped.
        ['{"tool": "quotes"}', '{"answer": "Sure.", "conclusive": true, "stance": "certain"}'],
    ],
)
async def test_otherwise_it_is_no_conclusion(replies: list[str]) -> None:
    analyst = PredictionAnalyst(service(ScriptedModel(*replies))[0], Finance())  # type: ignore[arg-type]
    assert (await analyst.read("local", "m1")).stance == "no_conclusion"
    assert "no_conclusion" in STANCES


async def test_unknown_market() -> None:
    analyst = PredictionAnalyst(service(ScriptedModel())[0], Finance())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await analyst.read("local", "nope")
