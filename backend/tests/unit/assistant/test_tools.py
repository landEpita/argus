from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from argus.domain.events import EventCategory, EventFeed, GeoEvent
from argus.domain.geo import GeoPoint
from argus.services.assistant.tools import Toolbox, ToolContext, ToolError, _box
from tests.fakes import make_aircraft
from tests.unit.domain.test_signals import story

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
CTX = ToolContext("local")


class Fakes:
    """Just enough of each service for the tools; records the calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def stories(self, **kw: Any) -> Any:
        self.calls.append(("stories", kw))
        return SimpleNamespace(items=[story("s1", ("UA",), 2)])

    async def country(self, iso2: str) -> Any:
        if iso2 == "ZZ":
            return None
        signal = SimpleNamespace(
            score=52.1,
            has_baseline=False,
            components=[
                SimpleNamespace(
                    component=SimpleNamespace(value="air_alerts"), points=15, max_points=15, raw=16
                )
            ],
        )
        return SimpleNamespace(name="Ukraine", signal=signal, stories=[story("s", ("UA",), 1)])

    async def convergence(self) -> Any:
        cell = SimpleNamespace(
            country="UA",
            center=GeoPoint(lat=49.23, lon=33.1),
            kinds=[SimpleNamespace(kind=SimpleNamespace(value="air_alert"), count=2)],
            latest=NOW,
        )
        return SimpleNamespace(items=[cell])

    async def events(self, feed: EventFeed, **kw: Any) -> Any:
        self.calls.append(("events", {"feed": feed, **kw}))
        e = GeoEvent(
            id="1", category=EventCategory.ARMED_CONFLICT, title="Clash",
            position=GeoPoint(lat=15, lon=42), occurred_at=NOW, source="gdelt",
        )  # fmt: skip
        return SimpleNamespace(items=[e])

    async def military(self, query: Any) -> Any:
        self.calls.append(("military", {"bbox": query.bbox}))
        return [make_aircraft("ae01ce")]

    async def quotes(self) -> Any:
        q = SimpleNamespace(
            instrument=SimpleNamespace(symbol="BZ=F", name="Brent", unit="USD/bbl"),
            price=97.44,
            change_pct=-8.59,
        )
        return SimpleNamespace(items=[q], missing=[SimpleNamespace(key="^N225")])

    async def asset(self, symbol: str, range_: Any) -> Any:
        def candle(close: float) -> Any:
            return SimpleNamespace(close=close)

        technicals = SimpleNamespace(
            close=110, sma_50=100, sma_200=90, rsi_14=71.2, high_52w=112, low_52w=70,
            levels=[
                SimpleNamespace(kind=SimpleNamespace(value="resistance"), price=112, touches=3)
            ],
        )  # fmt: skip
        history = SimpleNamespace(
            instrument=SimpleNamespace(name="Brent"), candles=[candle(100), candle(110)]
        )
        return SimpleNamespace(history=history, technicals=technicals)

    async def chokepoints(self) -> Any:
        def c(name: str, pct: float | None) -> Any:
            return SimpleNamespace(
                name=name, last_7d_avg=4.3, change_vs_last_year_pct=pct, change_vs_90d_pct=-70,
                latest_date=date(2026, 9, 20),
            )  # fmt: skip

        return [c("Suez", -10), c("Hormuz", -96.3), c("Panama", None)]


def toolbox() -> tuple[Toolbox, Fakes]:
    f = Fakes()
    return Toolbox(finance=f, analysis=f, news=f, events=f, aviation=f), f  # type: ignore[arg-type]


def test_the_catalogue_lists_every_tool_and_argument() -> None:
    box, _ = toolbox()
    text = box.catalogue()
    assert "- situations(no arguments):" in text
    assert "symbol: Yahoo symbol" in text
    assert len(text.splitlines()) == len(box.tools) == 9


async def test_news_and_country() -> None:
    box, f = toolbox()
    news = await box.tools["news"].run({"query": "Kyiv", "country": "ua", "hours": 500}, CTX)
    assert news.data["count"] == 1
    assert news.sources == ("S0", "S1")
    assert f.calls[0][1]["country"] == "UA"
    assert f.calls[0][1]["window"].total_seconds() == 72 * 3600  # capped
    country = await box.tools["country"].run({"iso2": "ua"}, CTX)
    assert country.data["components"] == {"air_alerts": {"points": 15, "of": 15, "input": 16}}
    assert "not a stability measure" in country.data["note"]
    with pytest.raises(ToolError):
        await box.tools["country"].run({"iso2": "ZZ"}, CTX)
    with pytest.raises(ToolError):
        await box.tools["country"].run({"iso2": "Ukraine"}, CTX)


async def test_events_near_a_point_flag_press_coding() -> None:
    box, f = toolbox()
    out = await box.tools["events"].run(
        {"feed": "conflict", "lat": 15, "lon": 42, "radius_km": 200}, CTX
    )
    assert out.data["count"] == 1
    assert "leads, not facts" in out.data["note"]
    assert out.sources == ("GDELT (unverified)",)
    assert f.calls[0][1]["bbox"].contains(GeoPoint(lat=15, lon=42))
    with pytest.raises(ToolError):
        await box.tools["events"].run({"feed": "gossip", "lat": 0, "lon": 0}, CTX)
    with pytest.raises(ToolError):
        await box.tools["events"].run({"feed": "earthquakes", "lat": "north", "lon": 0}, CTX)


async def test_military_quotes_asset_situations_chokepoints() -> None:
    box, _ = toolbox()
    mil = await box.tools["military_aircraft"].run({"lat": 26, "lon": 56}, CTX)
    assert mil.data["count"] == 1
    quotes = await box.tools["quotes"].run({}, CTX)
    assert quotes.data["missing"] == ["^N225"]
    asset = await box.tools["asset"].run({"symbol": "bz=f"}, CTX)
    assert asset.data["change_3m_pct"] == 10.0
    assert asset.data["levels"] == [{"kind": "resistance", "price": 112, "touches": 3}]
    with pytest.raises(ToolError):
        await box.tools["asset"].run({"symbol": "BZ F"}, CTX)
    situations = await box.tools["situations"].run({}, CTX)
    assert situations.data["situations"][0]["kinds"] == {"air_alert": 2}
    choke = await box.tools["chokepoints"].run({}, CTX)
    assert [c["name"] for c in choke.data["chokepoints"]] == ["Hormuz", "Suez", "Panama"]


def test_search_boxes_are_clamped() -> None:
    box = _box(89.9, 179.9, 5000)
    assert (box.north, box.east) == (90, 180)
    with pytest.raises(ToolError):
        _box(91, 0, 100)
