"""
The assistant's tools: read-only views over Argus' services.

Every tool returns compact JSON-able data and the names of the sources it
read, so the answer's sources are what was actually consulted — not what the
model claims. Press-coded and state-media data carry their caveat in the data.
"""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

from argus.domain.aviation import AircraftQuery
from argus.domain.events import EventFeed
from argus.domain.geo import BoundingBox
from argus.domain.markets import SYMBOL_PATTERN, HistoryRange
from argus.services.analysis import AnalysisService
from argus.services.assistant.search import SearchService
from argus.services.aviation import AviationService
from argus.services.events import EventsService
from argus.services.finance import FinanceService
from argus.services.news import NewsService

LIST_LIMIT = 8
UNVERIFIED_FEEDS = {EventFeed.CONFLICT}
FEED_SOURCES = {
    EventFeed.EARTHQUAKES: "USGS",
    EventFeed.NATURAL_EVENTS: "NASA EONET",
    EventFeed.DISASTER_ALERTS: "GDACS",
    EventFeed.CONFLICT: "GDELT (unverified)",
    EventFeed.AIR_ALERTS: "Ukraine air-raid alerts",
    EventFeed.INTERNET_OUTAGES: "IODA",
    EventFeed.FIRES: "NASA FIRMS",
    EventFeed.LAUNCHES: "Launch Library 2",
}


class ToolError(ValueError):
    """Bad arguments from the model; reported back to it so it can correct itself."""


@dataclass(frozen=True, slots=True)
class ToolOutput:
    data: Any
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Who is asking: some tools read the owner's own settings (channels, models)."""

    owner: str


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    args: Mapping[str, str]
    run: Callable[[Mapping[str, Any], ToolContext], Awaitable[ToolOutput]] = field(repr=False)


class ToolSet(Protocol):
    """What the agent needs from a toolbox."""

    @property
    def tools(self) -> Mapping[str, Tool]: ...

    def catalogue(self) -> str: ...


def _num(args: Mapping[str, Any], key: str, default: float | None = None) -> float:
    value = args.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"'{key}' must be a number") from exc


def _box(lat: float, lon: float, radius_km: float) -> BoundingBox:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ToolError("lat must be in -90..90 and lon in -180..180")
    radius_km = min(max(radius_km, 10), 2000)
    dlat = radius_km / 111.0
    dlon = radius_km / max(111.0 * math.cos(math.radians(lat)), 1.0)
    return BoundingBox(
        west=max(-180, lon - dlon),
        south=max(-90, lat - dlat),
        east=min(180, lon + dlon),
        north=min(90, lat + dlat),
    )


class Toolbox:
    def __init__(
        self,
        *,
        finance: FinanceService,
        analysis: AnalysisService,
        news: NewsService,
        events: EventsService,
        aviation: AviationService,
        search: SearchService | None = None,
    ) -> None:
        self._search = search
        self._finance = finance
        self._analysis = analysis
        self._news = news
        self._events = events
        self._aviation = aviation
        where = {
            "lat": "number — latitude of the centre",
            "lon": "number — longitude of the centre",
            "radius_km": "number — search radius, default 300",
        }
        self.tools: dict[str, Tool] = {
            t.name: t
            for t in (
                Tool("news", "News stories clustered across outlets, newest first.",
                     {"query": "words to find in the (English) headlines, e.g. Red Sea (optional)",
                      "country": "ISO 3166-1 alpha-2 code (optional)",
                      "hours": "number — look-back window, default 24"}, self.news),
                Tool("country", "A country's signal index (0-100) and how it is made.",
                     {"iso2": "ISO 3166-1 alpha-2 code, e.g. UA"}, self.country),
                Tool("situations", "Places where several kinds of signal converge now.",
                     {}, self.situations),
                Tool("events", "Events near a point: earthquakes, disaster-alerts, conflict "
                     "(press-coded, unverified), air-alerts, internet-outages, natural-events.",
                     {"feed": "exactly one of: earthquakes, disaster-alerts, conflict, "
                      "air-alerts, internet-outages, natural-events",
                      **where, "hours": "number, default 24"},
                     self.events_near),
                Tool("military_aircraft", "Aircraft flagged as military near a point, right now.",
                     where, self.military_near),
                Tool("quotes", "Delayed prices of the market watch set (indices, oil, gas, "
                     "metals, FX, rates).", {}, self.quotes),
                Tool("asset", "Price history reading of one instrument: averages, RSI, "
                     "52-week range, support and resistance.",
                     {"symbol": "Yahoo symbol, e.g. BZ=F, ^GSPC, AAPL"}, self.asset),
                Tool("chokepoints", "Ship traffic through strategic straits vs last year.",
                     {}, self.chokepoints),
                Tool("search", "Search the last days of news stories and the user's Telegram "
                     "channels by words (and by meaning when available). Best for a topic "
                     "or a place name.",
                     {"query": "what to look for, e.g. Red Sea shipping",
                      "hours": "number — look-back window, default 72"}, self.search),
            )
        }  # fmt: skip

    def catalogue(self) -> str:
        lines = []
        for t in self.tools.values():
            args = ", ".join(f"{k}: {v}" for k, v in t.args.items()) or "no arguments"
            lines.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(lines)

    # ── Tools ───────────────────────────────────────────────────────────────

    async def news(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        hours = min(max(_num(args, "hours", 24), 1), 72)
        country = args.get("country")
        page = await self._news.stories(
            window=timedelta(hours=hours),
            limit=LIST_LIMIT,
            country=str(country).upper() if country else None,
            query=str(args["query"]) if args.get("query") else None,
        )
        items = [
            {
                "title": s.title,
                "outlets": [src.name for src in s.sources],
                "state_media_only": s.state_media_only,
                "countries": list(s.countries),
                "last_updated": s.last_updated.isoformat(timespec="minutes"),
            }
            for s in page.items
        ]
        outlets = sorted({src.name for s in page.items for src in s.sources})
        return ToolOutput({"stories": items, "count": len(items)}, tuple(outlets) or ("News",))

    async def country(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        iso2 = str(args.get("iso2", "")).upper()
        if len(iso2) != 2 or not iso2.isalpha():
            raise ToolError("iso2 must be a 2-letter country code")
        detail = await self._analysis.country(iso2)
        if detail is None:
            raise ToolError(f"unknown country {iso2}")
        s = detail.signal
        data = {
            "name": detail.name,
            "score": s.score if s else 0,
            "has_baseline": s.has_baseline if s else False,
            "components": {
                c.component.value: {"points": c.points, "of": c.max_points, "input": c.raw}
                for c in (s.components if s else ())
            },
            "stories": [st.title for st in detail.stories[:5]],
            "note": "Signal index: disruptive activity reported now, not a stability measure. "
            "reported_violence is press-coded and unverified.",
        }
        return ToolOutput(data, ("Argus signal index", "GDELT (unverified)", "News"))

    async def situations(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        result = await self._analysis.convergence()
        items = [
            {
                "country": c.country,
                "lat": round(c.center.lat, 1),
                "lon": round(c.center.lon, 1),
                "kinds": {k.kind.value: k.count for k in c.kinds},
                "latest": c.latest.isoformat(timespec="minutes"),
            }
            for c in result.items[:LIST_LIMIT]
        ]
        return ToolOutput(
            {"situations": items, "note": "reported_violence is press-coded, unverified"},
            ("Argus convergence",),
        )

    async def events_near(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        try:
            feed = EventFeed(str(args.get("feed")))
        except ValueError as exc:
            raise ToolError(f"feed must be one of {[f.value for f in EventFeed]}") from exc
        box = _box(_num(args, "lat"), _num(args, "lon"), _num(args, "radius_km", 300))
        hours = min(max(_num(args, "hours", 24), 1), 24 * 7)
        page = await self._events.events(feed, window=timedelta(hours=hours), bbox=box, limit=200)
        items = [
            {
                "title": e.title,
                "at": e.occurred_at.isoformat(timespec="minutes"),
                "magnitude": e.magnitude,
                "severity": e.severity,
            }
            for e in page.items[:LIST_LIMIT]
        ]
        data: dict[str, Any] = {"feed": feed.value, "count": len(page.items), "items": items}
        if feed in UNVERIFIED_FEEDS:
            data["note"] = "automated coding of press reports: leads, not facts"
        return ToolOutput(data, (FEED_SOURCES.get(feed, feed.value),))

    async def military_near(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        box = _box(_num(args, "lat"), _num(args, "lon"), _num(args, "radius_km", 300))
        aircraft = await self._aviation.military(AircraftQuery(bbox=box))
        data = {
            "count": len(aircraft),
            "aircraft": [
                {"callsign": a.callsign, "type": a.type_code, "altitude_m": a.altitude_m}
                for a in aircraft[:LIST_LIMIT]
            ],
            "note": "flagged from transponder databases; not exhaustive",
        }
        return ToolOutput(data, ("adsb.lol",))

    async def quotes(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        board = await self._finance.quotes()
        items = [
            {
                "symbol": q.instrument.symbol,
                "name": q.instrument.name,
                "price": q.price,
                "change_pct": q.change_pct,
                "unit": q.instrument.unit,
            }
            for q in board.items
        ]
        return ToolOutput(
            {"quotes": items, "missing": [m.key for m in board.missing], "delayed": True},
            ("Yahoo Finance (delayed)",),
        )

    async def asset(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        symbol = str(args.get("symbol", "")).upper()
        if not re.fullmatch(SYMBOL_PATTERN, symbol):
            raise ToolError("symbol must be a Yahoo symbol such as BZ=F")
        detail = await self._finance.asset(symbol, HistoryRange.QUARTER)
        t = detail.technicals
        candles = detail.history.candles
        data: dict[str, Any] = {"name": detail.history.instrument.name, "symbol": symbol}
        if candles:
            first, last = candles[0], candles[-1]
            data["change_3m_pct"] = round((last.close - first.close) / first.close * 100, 2)
        if t:
            data |= {
                "close": t.close,
                "sma_50": t.sma_50,
                "sma_200": t.sma_200,
                "rsi_14": t.rsi_14,
                "high_52w": t.high_52w,
                "low_52w": t.low_52w,
                "levels": [
                    {"kind": lv.kind.value, "price": lv.price, "touches": lv.touches}
                    for lv in t.levels
                ],
                "note": "descriptive reading of past prices, not a forecast",
            }
        return ToolOutput(data, ("Yahoo Finance (delayed)",))

    async def chokepoints(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        items = await self._finance.chokepoints()
        worst = sorted(items, key=lambda c: c.change_vs_last_year_pct or 0.0)[:LIST_LIMIT]
        data = [
            {
                "name": c.name,
                "ships_per_day_7d": c.last_7d_avg,
                "vs_same_week_last_year_pct": c.change_vs_last_year_pct,
                "vs_prior_90d_pct": c.change_vs_90d_pct,
                "data_as_of": c.latest_date.isoformat(),
            }
            for c in worst
        ]
        return ToolOutput({"chokepoints": data}, ("IMF PortWatch",))

    async def search(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolOutput:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required")
        if self._search is None:
            raise ToolError("search is not available")
        hours = min(max(_num(args, "hours", 72), 1), 168)
        result = await self._search.search(ctx.owner, query[:200], hours=hours)
        hits = [
            {
                "title": h.document.title,
                "kind": h.document.kind.value,
                "source": h.document.source,
                "at": h.document.at.isoformat(timespec="minutes"),
                "unverified": h.document.unverified,
                "match": h.match.value,
            }
            for h in result.hits
        ]
        data: dict[str, Any] = {
            "hits": hits,
            "searched": result.corpus,
            "by_meaning": result.semantic,
        }
        if result.note:
            data["note"] = result.note
        sources = sorted({h.document.source.split(",")[0] for h in result.hits}) or ["News"]
        return ToolOutput(data, tuple(sources))
