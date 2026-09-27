"""Markets: quotes for a curated watch set, crypto, funding rates, prediction markets."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability


class AssetClass(StrEnum):
    INDEX = "index"
    COMMODITY = "commodity"
    FX = "fx"
    RATE = "rate"
    VOLATILITY = "volatility"
    EQUITY = "equity"
    FUND = "fund"
    CRYPTO = "crypto"


class Instrument(DomainModel):
    symbol: str = Field(description="Provider-neutral symbol (Yahoo notation: ^GSPC, CL=F…)")
    name: str
    asset_class: AssetClass
    unit: str | None = Field(default=None, description="'USD/bbl', '%', 'pts'…")


class Quote(DomainModel):
    instrument: Instrument
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    day_low: float | None = Field(default=None, description="Session range, when the feed has it")
    day_high: float | None = None
    currency: str | None = None
    as_of: datetime = Field(description="Exchange time of the price, not fetch time")
    history: tuple[float, ...] = Field(default=(), description="Recent daily closes, oldest first")
    source: str
    delayed: bool = Field(default=True, description="Free feeds are delayed ~15 min or more")


class QuoteQuery(DomainModel):
    instrument: Instrument


# Yahoo notation: letters, digits and ^ = . - (^GSPC, CL=F, BRK-B, 7203.T).
SYMBOL_PATTERN = r"^[A-Za-z0-9^=.\-]{1,20}$"


class HistoryRange(StrEnum):
    MONTH = "1mo"
    QUARTER = "3mo"
    HALF_YEAR = "6mo"
    YEAR = "1y"
    TWO_YEARS = "2y"
    FIVE_YEARS = "5y"


class Candle(DomainModel):
    day: date = Field(description="Trading day, in the exchange's time zone")
    open: float
    high: float
    low: float
    close: float
    volume: float | None = Field(default=None, description="None when the feed has none (FX)")


class HistoryQuery(DomainModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    range: HistoryRange = HistoryRange.TWO_YEARS


class PriceHistory(DomainModel):
    instrument: Instrument
    currency: str | None = None
    exchange: str | None = None
    candles: tuple[Candle, ...] = Field(description="Daily bars, oldest first")
    source: str


class CryptoAsset(DomainModel):
    id: str
    symbol: str
    name: str
    price_usd: float
    change_24h_pct: float | None = None
    change_7d_pct: float | None = None
    market_cap_usd: float | None = None
    volume_24h_usd: float | None = None
    updated_at: datetime | None = None
    source: str


class CryptoQuery(DomainModel):
    limit: int = Field(default=20, ge=1, le=250)


class FundingRate(DomainModel):
    symbol: str = Field(description="'BTC', 'ETH'")
    exchange: str
    rate: float = Field(description="Per funding interval (8 h), as a fraction")
    annualized_pct: float
    mark_price: float | None = None
    next_funding_at: datetime | None = None


class FundingQuery(DomainModel):
    symbol: str = Field(pattern=r"^[A-Z]{2,10}$")


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class Liquidation(DomainModel):
    position: Side = Field(description="The side that was liquidated")
    price: float = Field(description="Bankruptcy price")
    size: float = Field(description="In the base asset (BTC…)")
    notional_usd: float
    at: datetime


class LiquidationQuery(DomainModel):
    symbol: str = Field(pattern=r"^[A-Z]{2,10}$")


class LiquidationSummary(DomainModel):
    symbol: str
    exchange: str
    count: int
    since: datetime | None = Field(description="Oldest liquidation in the sample")
    until: datetime | None
    long_usd: float = Field(description="Longs liquidated (forced sells)")
    short_usd: float = Field(description="Shorts liquidated (forced buys)")
    largest: tuple[Liquidation, ...]
    note: str = Field(description="What the sample covers; one exchange is not the market")


class Outcome(DomainModel):
    label: str
    probability: float = Field(ge=0, le=1)


class PredictionMarket(DomainModel):
    id: str
    question: str
    event_title: str
    outcomes: tuple[Outcome, ...]
    one_day_change: float | None = Field(default=None, description="Change of the first outcome")
    volume_usd: float | None = None
    volume_24h_usd: float | None = None
    end_date: datetime | None = None
    url: str
    source: str


class PredictionQuery(DomainModel):
    tag: str = Field(default="geopolitics", pattern=r"^[a-z0-9-]+$")
    limit: int = Field(default=30, ge=1, le=100)


QUOTE: Capability[QuoteQuery, Quote] = Capability(
    "markets.quote", "Latest price and recent daily closes for one instrument."
)
CRYPTO_MARKETS: Capability[CryptoQuery, list[CryptoAsset]] = Capability(
    "markets.crypto", "Largest crypto assets by market capitalisation."
)
FUNDING_RATES: Capability[FundingQuery, FundingRate] = Capability(
    "markets.funding", "Perpetual futures funding rate for one asset."
)
PRICE_HISTORY: Capability[HistoryQuery, PriceHistory] = Capability(
    "markets.price_history", "Daily OHLC bars for one symbol."
)
LIQUIDATIONS: Capability[LiquidationQuery, LiquidationSummary] = Capability(
    "markets.liquidations", "Recent forced liquidations of perpetual futures for one asset."
)
PREDICTION_MARKETS: Capability[PredictionQuery, list[PredictionMarket]] = Capability(
    "markets.prediction", "Open prediction markets, most traded first."
)

# The default watch set. Symbols use Yahoo notation, which OpenBB's yfinance provider shares.
WATCH_SET: tuple[Instrument, ...] = (
    Instrument(symbol="^GSPC", name="S&P 500", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="^IXIC", name="Nasdaq Composite", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="^STOXX50E", name="Euro Stoxx 50", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="^STOXX", name="STOXX 600", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="^N225", name="Nikkei 225", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="000300.SS", name="CSI 300", asset_class=AssetClass.INDEX, unit="pts"),
    Instrument(symbol="^VIX", name="VIX", asset_class=AssetClass.VOLATILITY, unit="pts"),
    Instrument(symbol="BZ=F", name="Brent crude", asset_class=AssetClass.COMMODITY, unit="USD/bbl"),
    Instrument(symbol="CL=F", name="WTI crude", asset_class=AssetClass.COMMODITY, unit="USD/bbl"),
    Instrument(
        symbol="NG=F", name="US natural gas", asset_class=AssetClass.COMMODITY, unit="USD/MMBtu"
    ),
    Instrument(
        symbol="TTF=F", name="Dutch TTF gas", asset_class=AssetClass.COMMODITY, unit="EUR/MWh"
    ),
    Instrument(symbol="GC=F", name="Gold", asset_class=AssetClass.COMMODITY, unit="USD/oz"),
    Instrument(symbol="SI=F", name="Silver", asset_class=AssetClass.COMMODITY, unit="USD/oz"),
    Instrument(symbol="HG=F", name="Copper", asset_class=AssetClass.COMMODITY, unit="USD/lb"),
    Instrument(symbol="ZW=F", name="Wheat", asset_class=AssetClass.COMMODITY, unit="USc/bu"),
    Instrument(symbol="DX-Y.NYB", name="US dollar index", asset_class=AssetClass.FX, unit="pts"),
    Instrument(symbol="EURUSD=X", name="EUR/USD", asset_class=AssetClass.FX),
    Instrument(symbol="JPY=X", name="USD/JPY", asset_class=AssetClass.FX),
    Instrument(symbol="CNY=X", name="USD/CNY", asset_class=AssetClass.FX),
    Instrument(symbol="^TNX", name="US 10-year yield", asset_class=AssetClass.RATE, unit="%"),
)


def find_instrument(symbol: str) -> Instrument | None:
    """The curated description of a watch-set symbol, if it is one."""
    return next((i for i in WATCH_SET if i.symbol == symbol), None)
