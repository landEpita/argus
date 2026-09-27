from datetime import UTC, datetime
from typing import Any

from argus.domain.geo import GeoPoint
from argus.domain.markets import WATCH_SET, Quote
from argus.services.assistant.notes import NotesService, market_facts
from argus.services.finance import Board
from tests.fakes import FakeWallClock
from tests.unit.assistant.test_agent import NOW, ScriptedModel, service


class Finance:
    async def quotes(self) -> Board[Quote]:
        def q(symbol: str, pct: float) -> Quote:
            instrument = next(i for i in WATCH_SET if i.symbol == symbol)
            return Quote(instrument=instrument, price=100, change_pct=pct, as_of=NOW, source="t")

        return Board(
            items=[q("^GSPC", 0.5), q("BZ=F", -8.59), q("TTF=F", 2.1), q("^VIX", -1.0)],
            missing=[],
        )

    async def chokepoints(self) -> list[Any]:
        from argus.domain.chokepoints import ChokepointTraffic

        return [
            ChokepointTraffic(
                id="h", name="Strait of Hormuz", position=GeoPoint(lat=26, lon=56),
                latest_date=datetime(2026, 9, 20, tzinfo=UTC).date(), last_7d_avg=4.3,
                prior_90d_avg=15, last_year_avg=116, change_vs_90d_pct=-71.9,
                change_vs_last_year_pct=-96.3, tanker_share_pct=None, daily=(), source="t",
            )
        ]  # fmt: skip


async def test_facts_are_the_biggest_moves_and_collapsed_straits() -> None:
    facts = await market_facts(Finance())  # type: ignore[arg-type]
    assert facts == [
        "Brent crude −8.59 % on the session",
        "Dutch TTF gas +2.10 % on the session",
        "VIX −1.00 % on the session",
        "Strait of Hormuz traffic −96.30 % vs the same week last year",
    ]


async def test_the_model_writes_the_note_when_it_sticks_to_the_facts() -> None:
    model = ScriptedModel("Brent fell 8.59 % while Hormuz traffic is 96.30 % below last year.")
    notes = NotesService(service(model)[0], Finance(), FakeWallClock(NOW))  # type: ignore[arg-type]
    note = await notes.market("local")
    assert note.written_by == "ollama/mistral"
    assert note.text.startswith("Brent fell 8.59 %")
    assert note.rejected == []


async def test_invented_figures_fall_back_to_the_template() -> None:
    model = ScriptedModel("Brent fell 8.59 % on a 3.2 % OPEC cut.")
    notes = NotesService(service(model)[0], Finance(), FakeWallClock(NOW))  # type: ignore[arg-type]
    note = await notes.market("local")
    assert note.written_by == "template"
    assert note.rejected == ["3.2"]
    assert note.text.startswith("Brent crude −8.59 % on the session; ")


async def test_without_a_model_the_note_is_the_template() -> None:
    svc = service(ScriptedModel(), configured=False)[0]
    note = await NotesService(svc, Finance(), FakeWallClock(NOW)).market("local")  # type: ignore[arg-type]
    assert note.written_by == "template"
    assert note.facts
