"""
Markets, macro and chokepoints: thin orchestration over the capabilities.

Quotes are fetched per instrument through the registry, so each symbol gets
the provider fallback on its own and a single bad symbol only removes itself
from the board (it is listed under ``missing`` with the reason).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from argus.domain.chokepoints import CHOKEPOINT_TRAFFIC, ChokepointQuery, ChokepointTraffic
from argus.domain.energy import (
    ENERGY_SERIES,
    SERIES,
    EnergySeriesQuery,
    EnergySeriesSpec,
    EnergyStock,
    Reading,
    summarise,
)
from argus.domain.macro import (
    ECONOMIC_CALENDAR,
    SENTIMENT,
    YIELD_CURVE,
    CalendarEvent,
    EmptyQuery,
    SentimentIndex,
    YieldCurve,
)
from argus.domain.markets import (
    CRYPTO_MARKETS,
    FUNDING_RATES,
    LIQUIDATIONS,
    PREDICTION_MARKETS,
    PRICE_HISTORY,
    QUOTE,
    WATCH_SET,
    CryptoAsset,
    CryptoQuery,
    FundingQuery,
    FundingRate,
    HistoryQuery,
    HistoryRange,
    Instrument,
    LiquidationQuery,
    LiquidationSummary,
    PredictionMarket,
    PredictionQuery,
    PriceHistory,
    Quote,
    QuoteQuery,
)
from argus.domain.technicals import Technicals, analyse
from argus.infra.cache import Cache, get_or_set_with_fallback
from argus.infra.codec import PydanticCodec
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.providers.registry import ProviderRegistry

QUOTE_TTL_S = 60.0
QUOTE_CONCURRENCY = 4
_MISSING = (AllProvidersFailedError, NoProviderError)


@dataclass(frozen=True, slots=True)
class Missing:
    key: str
    error: str


@dataclass(frozen=True, slots=True)
class Board[T]:
    items: list[T]
    missing: list[Missing]


@dataclass(frozen=True, slots=True)
class AssetDetail:
    history: PriceHistory  # trimmed to the requested range
    technicals: Technicals | None  # always read on at least two years of bars


HISTORY_TTL_S = 15 * 60.0
_RANGE_DAYS = {
    HistoryRange.MONTH: 31,
    HistoryRange.QUARTER: 92,
    HistoryRange.HALF_YEAR: 183,
    HistoryRange.YEAR: 366,
    HistoryRange.TWO_YEARS: 731,
    HistoryRange.FIVE_YEARS: 1827,
}


class FinanceService:
    def __init__(self, registry: ProviderRegistry, cache: Cache) -> None:
        self._registry = registry
        self._cache = cache
        self._semaphore = asyncio.Semaphore(QUOTE_CONCURRENCY)

    # ── Markets ──────────────────────────────────────────────────────────────

    async def quotes(self, instruments: Sequence[Instrument] = WATCH_SET) -> Board[Quote]:
        results = await asyncio.gather(*(self._quote(i) for i in instruments))
        return Board(
            items=[q for q, _ in results if q is not None],
            missing=[m for _, m in results if m is not None],
        )

    async def _quote(self, instrument: Instrument) -> tuple[Quote | None, Missing | None]:
        async def fetch() -> Quote:
            async with self._semaphore:
                return await self._registry.fetch(QUOTE, QuoteQuery(instrument=instrument))

        try:
            quote = await get_or_set_with_fallback(
                self._cache,
                f"{QUOTE.name}:{instrument.symbol}",
                QUOTE_TTL_S,
                86400.0,
                fetch,
                _QUOTE,
                recoverable=(AllProvidersFailedError,),
            )
        except _MISSING as exc:
            return None, Missing(instrument.symbol, str(exc))
        return quote, None

    async def crypto(self, limit: int = 20) -> list[CryptoAsset]:
        query = CryptoQuery(limit=limit)
        return await get_or_set_with_fallback(
            self._cache, f"{CRYPTO_MARKETS.name}:{limit}", 120.0, 86400.0,
            lambda: self._registry.fetch(CRYPTO_MARKETS, query), _CRYPTO,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    async def funding(self, symbols: Sequence[str]) -> Board[FundingRate]:
        async def one(symbol: str) -> tuple[FundingRate | None, Missing | None]:
            query = FundingQuery(symbol=symbol)
            try:
                rate = await self._cache.get_or_set(
                    f"{FUNDING_RATES.name}:{symbol}",
                    300.0,
                    lambda: self._registry.fetch(FUNDING_RATES, query),
                    _FUNDING,
                )
            except _MISSING as exc:
                return None, Missing(symbol, str(exc))
            return rate, None

        results = await asyncio.gather(*(one(s) for s in symbols))
        return Board(
            items=[r for r, _ in results if r is not None],
            missing=[m for _, m in results if m is not None],
        )

    async def asset(self, symbol: str, range_: HistoryRange) -> AssetDetail:
        """
        One fetch serves every range up to two years, so the 200-day average
        and the levels do not depend on the zoom of the chart.
        """
        fetched = (
            HistoryRange.FIVE_YEARS if range_ is HistoryRange.FIVE_YEARS else HistoryRange.TWO_YEARS
        )
        query = HistoryQuery(symbol=symbol, range=fetched)
        full = await get_or_set_with_fallback(
            self._cache, f"{PRICE_HISTORY.name}:{symbol}:{fetched.value}", HISTORY_TTL_S, 86400.0,
            lambda: self._registry.fetch(PRICE_HISTORY, query), _HISTORY,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip
        shown = full.candles
        if shown:
            start = shown[-1].day - timedelta(days=_RANGE_DAYS[range_])
            shown = tuple(c for c in shown if c.day > start)
        return AssetDetail(
            history=full.model_copy(update={"candles": shown}),
            technicals=analyse(full.candles),
        )

    async def liquidations(self, symbols: Sequence[str]) -> Board[LiquidationSummary]:
        async def one(symbol: str) -> tuple[LiquidationSummary | None, Missing | None]:
            query = LiquidationQuery(symbol=symbol)
            try:
                summary = await self._cache.get_or_set(
                    f"{LIQUIDATIONS.name}:{symbol}",
                    120.0,
                    lambda: self._registry.fetch(LIQUIDATIONS, query),
                    _LIQUIDATIONS,
                )
            except _MISSING as exc:
                return None, Missing(symbol, str(exc))
            return summary, None

        results = await asyncio.gather(*(one(s) for s in symbols))
        return Board(
            items=[r for r, _ in results if r is not None],
            missing=[m for _, m in results if m is not None],
        )

    async def prediction(self, tag: str, limit: int) -> list[PredictionMarket]:
        query = PredictionQuery(tag=tag, limit=limit)
        return await get_or_set_with_fallback(
            self._cache, f"{PREDICTION_MARKETS.name}:{tag}:{limit}", 300.0, 86400.0,
            lambda: self._registry.fetch(PREDICTION_MARKETS, query), _PREDICTION,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    # ── Macro ────────────────────────────────────────────────────────────────

    async def sentiment(self) -> list[SentimentIndex]:
        return await get_or_set_with_fallback(
            self._cache, SENTIMENT.name, 3600.0, 3 * 86400.0,
            lambda: self._registry.fetch(SENTIMENT, EmptyQuery()), _SENTIMENT,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    async def yield_curve(self) -> YieldCurve:
        return await get_or_set_with_fallback(
            self._cache, YIELD_CURVE.name, 6 * 3600.0, 7 * 86400.0,
            lambda: self._registry.fetch(YIELD_CURVE, EmptyQuery()), _CURVE,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    async def calendar(self) -> list[CalendarEvent]:
        return await get_or_set_with_fallback(
            self._cache, ECONOMIC_CALENDAR.name, 3600.0, 86400.0,
            lambda: self._registry.fetch(ECONOMIC_CALENDAR, EmptyQuery()), _CALENDAR,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    async def energy_stocks(self) -> Board[EnergyStock]:
        """Series are fetched one after the other: ``DEMO_KEY`` dislikes bursts."""
        items: list[EnergyStock] = []
        missing: list[Missing] = []
        for spec in SERIES:
            try:
                readings = await self._energy_series(spec)
            except AllProvidersFailedError as exc:  # disabled = 503 for the whole board
                missing.append(Missing(spec.id, str(exc)))
                continue
            stock = summarise(spec, readings, source="eia")
            if stock is None:
                missing.append(Missing(spec.id, "no readings"))
            else:
                items.append(stock)
        return Board(items=items, missing=missing)

    async def _energy_series(self, spec: EnergySeriesSpec) -> list[Reading]:
        query = EnergySeriesQuery(spec=spec)
        return await get_or_set_with_fallback(
            self._cache, f"{ENERGY_SERIES.name}:{spec.id}", 6 * 3600.0, 14 * 86400.0,
            lambda: self._registry.fetch(ENERGY_SERIES, query), _READINGS,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip

    # ── Chokepoints ──────────────────────────────────────────────────────────

    async def chokepoints(self) -> list[ChokepointTraffic]:
        return await get_or_set_with_fallback(
            self._cache, CHOKEPOINT_TRAFFIC.name, 6 * 3600.0, 7 * 86400.0,
            lambda: self._registry.fetch(CHOKEPOINT_TRAFFIC, ChokepointQuery()), _CHOKEPOINTS,
            recoverable=(AllProvidersFailedError,),
        )  # fmt: skip


_QUOTE: PydanticCodec[Quote] = PydanticCodec(Quote)
_HISTORY: PydanticCodec[PriceHistory] = PydanticCodec(PriceHistory)
_LIQUIDATIONS: PydanticCodec[LiquidationSummary] = PydanticCodec(LiquidationSummary)
_READINGS: PydanticCodec[list[Reading]] = PydanticCodec(list[Reading])
_CRYPTO: PydanticCodec[list[CryptoAsset]] = PydanticCodec(list[CryptoAsset])
_FUNDING: PydanticCodec[FundingRate] = PydanticCodec(FundingRate)
_PREDICTION: PydanticCodec[list[PredictionMarket]] = PydanticCodec(list[PredictionMarket])
_SENTIMENT: PydanticCodec[list[SentimentIndex]] = PydanticCodec(list[SentimentIndex])
_CURVE: PydanticCodec[YieldCurve] = PydanticCodec(YieldCurve)
_CALENDAR: PydanticCodec[list[CalendarEvent]] = PydanticCodec(list[CalendarEvent])
_CHOKEPOINTS: PydanticCodec[list[ChokepointTraffic]] = PydanticCodec(list[ChokepointTraffic])
