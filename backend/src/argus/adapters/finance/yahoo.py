"""
Yahoo Finance chart API (``/v8/finance/chart``), no key.

Unofficial and rate-limited: it answers 429 to browser-like User-Agents and
to bursts, so the markets service fetches a few symbols at a time. Prices are
delayed (15 min or more, depending on the exchange).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.domain.markets import (
    AssetClass,
    Candle,
    HistoryQuery,
    Instrument,
    PriceHistory,
    Quote,
    QuoteQuery,
    find_instrument,
)
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
# Yahoo rejects full browser User-Agents from servers but accepts this one.
HEADERS = {"User-Agent": "Mozilla/5.0"}
HISTORY_POINTS = 30


def quote_from_closes(
    instrument: Instrument,
    *,
    price: float,
    closes: list[float],
    at: datetime,
    currency: str | None,
    source: str,
    previous: float | None,
    day_low: float | None = None,
    day_high: float | None = None,
) -> Quote:
    change = None if previous is None else price - previous
    change_pct = None if change is None or not previous else change / previous * 100
    return Quote(
        instrument=instrument,
        price=round(price, 6),
        previous_close=previous,
        change=None if change is None else round(change, 6),
        change_pct=None if change_pct is None else round(change_pct, 3),
        day_low=day_low,
        day_high=day_high,
        currency=currency,
        as_of=at,
        history=tuple(round(c, 6) for c in closes[-HISTORY_POINTS:]),
        source=source,
    )


class YahooQuoteFetcher(Fetcher[QuoteQuery, Quote]):
    provider_name = "yahoo"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def transform_query(self, query: QuoteQuery) -> Mapping[str, str]:
        return {"symbol": query.instrument.symbol, "range": "3mo", "interval": "1d"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        symbol = params["symbol"]
        return await self._http.get_json(
            f"{self._base_url}/{symbol}",
            provider=self.provider_name,
            params={k: v for k, v in params.items() if k != "symbol"},
            headers=HEADERS,
        )

    def transform(self, query: QuoteQuery, raw: Any) -> Quote:
        instrument = query.instrument
        try:
            result = raw["chart"]["result"][0]
            meta = result["meta"]
            price = as_float(meta.get("regularMarketPrice"))
            at = meta.get("regularMarketTime")
            if price is None or not isinstance(at, int | float):
                raise ProviderResponseError(self.provider_name, f"{instrument.symbol}: no price")
            offset = timedelta(seconds=float(meta.get("gmtoffset") or 0))

            def session(ts: float) -> date:  # the trading day, in the exchange's time zone
                return (datetime.fromtimestamp(ts, tz=UTC) + offset).date()

            bars = [
                (session(ts), close)
                for ts, close in zip(
                    result.get("timestamp") or [],
                    (as_float(v) for v in result["indicators"]["quote"][0]["close"]),
                    strict=False,
                )
                if close is not None and isinstance(ts, int | float)
            ]
            today = session(at)
            # Dated, so a missing bar never shifts "yesterday" by a day.
            earlier = [close for day, close in bars if day < today]
            return quote_from_closes(
                instrument,
                price=price,
                closes=[close for _, close in bars],
                previous=earlier[-1] if earlier else as_float(meta.get("chartPreviousClose")),
                at=datetime.fromtimestamp(at, tz=UTC),
                currency=meta.get("currency"),
                source=self.provider_name,
                day_low=as_float(meta.get("regularMarketDayLow")),
                day_high=as_float(meta.get("regularMarketDayHigh")),
            )
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderResponseError(
                self.provider_name, f"{instrument.symbol}: unexpected chart payload"
            ) from exc


_ASSET_CLASSES = {
    "EQUITY": AssetClass.EQUITY,
    "ETF": AssetClass.FUND,
    "MUTUALFUND": AssetClass.FUND,
    "INDEX": AssetClass.INDEX,
    "FUTURE": AssetClass.COMMODITY,
    "CURRENCY": AssetClass.FX,
    "CRYPTOCURRENCY": AssetClass.CRYPTO,
}


def instrument_from_meta(symbol: str, meta: Mapping[str, Any]) -> Instrument:
    """The curated watch-set entry when there is one, else what Yahoo says."""
    known = find_instrument(symbol)
    if known is not None:
        return known
    return Instrument(
        symbol=symbol,
        name=str(meta.get("longName") or meta.get("shortName") or symbol),
        asset_class=_ASSET_CLASSES.get(str(meta.get("instrumentType")), AssetClass.EQUITY),
    )


class YahooHistoryFetcher(Fetcher[HistoryQuery, PriceHistory]):
    provider_name = "yahoo"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def transform_query(self, query: HistoryQuery) -> Mapping[str, str]:
        return {"symbol": query.symbol, "range": query.range.value, "interval": "1d"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            f"{self._base_url}/{params['symbol']}",
            provider=self.provider_name,
            params={k: v for k, v in params.items() if k != "symbol"},
            headers=HEADERS,
        )

    def transform(self, query: HistoryQuery, raw: Any) -> PriceHistory:
        try:
            result = raw["chart"]["result"][0]
            meta = result["meta"]
            offset = timedelta(seconds=float(meta.get("gmtoffset") or 0))
            bars = result["indicators"]["quote"][0]
            candles: list[Candle] = []
            for i, ts in enumerate(result.get("timestamp") or []):
                o, h, lo, c = (as_float(bars[k][i]) for k in ("open", "high", "low", "close"))
                if o is None or h is None or lo is None or c is None:
                    continue  # holiday or partial bar
                volume = as_float((bars.get("volume") or [None] * (i + 1))[i])
                candles.append(
                    Candle(
                        day=(datetime.fromtimestamp(ts, tz=UTC) + offset).date(),
                        open=round(o, 6),
                        high=round(h, 6),
                        low=round(lo, 6),
                        close=round(c, 6),
                        volume=volume or None,  # Yahoo reports 0 when it has none
                    )
                )
            return PriceHistory(
                instrument=instrument_from_meta(query.symbol, meta),
                currency=meta.get("currency"),
                exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
                candles=tuple(candles),
                source=self.provider_name,
            )
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderResponseError(
                self.provider_name, f"{query.symbol}: unexpected chart payload"
            ) from exc
