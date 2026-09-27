from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from argus.api.deps import FinanceServiceDep
from argus.domain.chokepoints import ChokepointTraffic
from argus.domain.energy import EnergyStock
from argus.domain.macro import CalendarEvent, SentimentIndex, YieldCurve
from argus.domain.markets import (
    SYMBOL_PATTERN,
    Candle,
    CryptoAsset,
    FundingRate,
    HistoryRange,
    Instrument,
    LiquidationSummary,
    PredictionMarket,
    Quote,
)
from argus.domain.technicals import Technicals

router = APIRouter(tags=["finance"])


class MissingOut(BaseModel):
    key: str
    error: str


class QuoteBoard(BaseModel):
    count: int
    items: list[Quote]
    missing: list[MissingOut]


class FundingBoard(BaseModel):
    count: int
    items: list[FundingRate]
    missing: list[MissingOut]


class LiquidationBoard(BaseModel):
    count: int
    items: list[LiquidationSummary]
    missing: list[MissingOut]


class EnergyBoard(BaseModel):
    count: int
    items: list[EnergyStock]
    missing: list[MissingOut]


class AssetOut(BaseModel):
    instrument: Instrument
    currency: str | None
    exchange: str | None
    range: HistoryRange
    candles: list[Candle]
    technicals: Technicals | None
    source: str
    delayed: bool = True


_SYMBOLS = Query(pattern=r"^[A-Za-z]{2,10}(,[A-Za-z]{2,10}){0,9}$")


@router.get("/markets/quotes", response_model=QuoteBoard)
async def quotes(service: FinanceServiceDep) -> QuoteBoard:
    """The default watch set: indices, commodities, FX, rates. Delayed prices."""
    board = await service.quotes()
    return QuoteBoard(
        count=len(board.items),
        items=board.items,
        missing=[MissingOut(key=m.key, error=m.error) for m in board.missing],
    )


@router.get("/markets/crypto", response_model=list[CryptoAsset])
async def crypto(
    service: FinanceServiceDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[CryptoAsset]:
    return await service.crypto(limit)


@router.get("/markets/funding", response_model=FundingBoard)
async def funding(
    service: FinanceServiceDep,
    symbols: Annotated[str, _SYMBOLS] = "BTC,ETH,SOL",
) -> FundingBoard:
    """Perpetual funding: positive = longs pay shorts (crowded long)."""
    board = await service.funding([s.upper() for s in symbols.split(",")])
    return FundingBoard(
        count=len(board.items),
        items=board.items,
        missing=[MissingOut(key=m.key, error=m.error) for m in board.missing],
    )


@router.get("/markets/assets/{symbol}", response_model=AssetOut)
async def asset(
    service: FinanceServiceDep,
    symbol: Annotated[str, Path(pattern=SYMBOL_PATTERN)],
    range: Annotated[HistoryRange, Query()] = HistoryRange.YEAR,
) -> AssetOut:
    """Daily bars and a technical reading (descriptive, not advice) for any Yahoo symbol."""
    detail = await service.asset(symbol, range)
    h = detail.history
    return AssetOut(
        instrument=h.instrument,
        currency=h.currency,
        exchange=h.exchange,
        range=range,
        candles=list(h.candles),
        technicals=detail.technicals,
        source=h.source,
    )


@router.get("/markets/liquidations", response_model=LiquidationBoard)
async def liquidations(
    service: FinanceServiceDep, symbols: Annotated[str, _SYMBOLS] = "BTC,ETH,SOL"
) -> LiquidationBoard:
    """Recent forced liquidations on one exchange: a sample, not the whole market."""
    board = await service.liquidations([s.upper() for s in symbols.split(",")])
    return LiquidationBoard(
        count=len(board.items),
        items=board.items,
        missing=[MissingOut(key=m.key, error=m.error) for m in board.missing],
    )


@router.get("/macro/energy-stocks", response_model=EnergyBoard)
async def energy_stocks(service: FinanceServiceDep) -> EnergyBoard:
    """Weekly US inventories vs the same week of the five previous years (EIA)."""
    board = await service.energy_stocks()
    if not board.items and board.missing:
        raise HTTPException(status_code=503, detail="no energy data")
    return EnergyBoard(
        count=len(board.items),
        items=board.items,
        missing=[MissingOut(key=m.key, error=m.error) for m in board.missing],
    )


@router.get("/markets/prediction", response_model=list[PredictionMarket])
async def prediction(
    service: FinanceServiceDep,
    tag: Annotated[str, Query(pattern=r"^[a-z0-9-]+$")] = "geopolitics",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[PredictionMarket]:
    """Open prediction markets. Prices are crowd probabilities, not forecasts of record."""
    return await service.prediction(tag, limit)


@router.get("/macro/sentiment", response_model=list[SentimentIndex])
async def sentiment(service: FinanceServiceDep) -> list[SentimentIndex]:
    return await service.sentiment()


@router.get("/macro/yield-curve", response_model=YieldCurve)
async def yield_curve(service: FinanceServiceDep) -> YieldCurve:
    return await service.yield_curve()


@router.get("/macro/calendar", response_model=list[CalendarEvent])
async def calendar(
    service: FinanceServiceDep,
    impact: Annotated[str | None, Query(pattern=r"^(high|medium|low|holiday)$")] = None,
) -> list[CalendarEvent]:
    events = await service.calendar()
    return [e for e in events if impact is None or e.impact.value == impact]


@router.get("/maritime/chokepoints", response_model=list[ChokepointTraffic])
async def chokepoints(service: FinanceServiceDep) -> list[ChokepointTraffic]:
    """Daily transits vs the same week last year and vs the prior 90 days (PortWatch)."""
    items = await service.chokepoints()
    if not items:
        raise HTTPException(status_code=503, detail="no chokepoint data")
    return sorted(items, key=lambda c: c.change_vs_last_year_pct or 0.0)
