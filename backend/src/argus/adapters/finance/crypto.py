"""CoinGecko markets and perpetual funding rates (Binance, then OKX). No keys."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, parse_utc
from argus.domain.markets import (
    CryptoAsset,
    CryptoQuery,
    FundingQuery,
    FundingRate,
    Liquidation,
    LiquidationQuery,
    LiquidationSummary,
    Side,
)
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

FUNDING_PERIODS_PER_YEAR = 3 * 365  # both venues settle every 8 hours


class CoinGeckoMarketsFetcher(Fetcher[CryptoQuery, list[CryptoAsset]]):
    provider_name = "coingecko"

    def __init__(
        self, http: HttpClient, base_url: str = "https://api.coingecko.com/api/v3"
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/coins/markets"

    def transform_query(self, query: CryptoQuery) -> Mapping[str, str]:
        return {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": str(query.limit),
            "page": "1",
            "price_change_percentage": "24h,7d",
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, params=params)

    def transform(self, query: CryptoQuery, raw: Any) -> list[CryptoAsset]:
        if not isinstance(raw, list):
            raise ProviderResponseError(self.provider_name, "expected a list of coins")
        assets: list[CryptoAsset] = []
        for coin in raw:
            try:
                price = as_float(coin.get("current_price"))
                if price is None:
                    continue
                assets.append(
                    CryptoAsset(
                        id=coin["id"],
                        symbol=str(coin["symbol"]).upper(),
                        name=coin["name"],
                        price_usd=price,
                        change_24h_pct=as_float(coin.get("price_change_percentage_24h")),
                        change_7d_pct=as_float(coin.get("price_change_percentage_7d_in_currency")),
                        market_cap_usd=as_float(coin.get("market_cap")),
                        volume_24h_usd=as_float(coin.get("total_volume")),
                        updated_at=parse_utc(coin.get("last_updated")),
                        source=self.provider_name,
                    )
                )
            except (KeyError, TypeError, AttributeError, ValidationError):
                continue
        return assets


def _funding(
    symbol: str, exchange: str, rate: float, mark: float | None, next_ms: Any
) -> FundingRate:
    next_at = (
        datetime.fromtimestamp(float(next_ms) / 1000, tz=UTC)
        if as_float(next_ms) is not None
        else None
    )
    return FundingRate(
        symbol=symbol,
        exchange=exchange,
        rate=rate,
        annualized_pct=round(rate * FUNDING_PERIODS_PER_YEAR * 100, 2),
        mark_price=mark,
        next_funding_at=next_at,
    )


class BinanceFundingFetcher(Fetcher[FundingQuery, FundingRate]):
    provider_name = "binance"

    def __init__(self, http: HttpClient, base_url: str = "https://fapi.binance.com") -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/fapi/v1/premiumIndex"

    def transform_query(self, query: FundingQuery) -> Mapping[str, str]:
        return {"symbol": f"{query.symbol}USDT"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, params=params)

    def transform(self, query: FundingQuery, raw: Any) -> FundingRate:
        rate = as_float(raw.get("lastFundingRate")) if isinstance(raw, dict) else None
        if rate is None:
            raise ProviderResponseError(self.provider_name, "no funding rate")
        return _funding(
            query.symbol,
            self.provider_name,
            rate,
            as_float(raw.get("markPrice")),
            raw.get("nextFundingTime"),
        )


class OkxFundingFetcher(Fetcher[FundingQuery, FundingRate]):
    provider_name = "okx"

    def __init__(self, http: HttpClient, base_url: str = "https://www.okx.com") -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/api/v5/public/funding-rate"

    def transform_query(self, query: FundingQuery) -> Mapping[str, str]:
        return {"instId": f"{query.symbol}-USDT-SWAP"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, params=params)

    def transform(self, query: FundingQuery, raw: Any) -> FundingRate:
        try:
            row = raw["data"][0]
            rate = as_float(row.get("fundingRate"))
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(self.provider_name, "no funding data") from exc
        if rate is None:
            raise ProviderResponseError(self.provider_name, "no funding rate")
        return _funding(query.symbol, self.provider_name, rate, None, row.get("fundingTime"))


LARGEST_LIQUIDATIONS = 5


class OkxLiquidationFetcher(Fetcher[LiquidationQuery, LiquidationSummary]):
    """
    The latest filled liquidations of OKX's USDT perpetual (up to 100 orders).

    Sizes come in contracts; the contract value (``ctVal``, 0.01 BTC for
    BTC-USDT-SWAP) is read from the instrument and remembered.
    """

    provider_name = "okx"

    def __init__(self, http: HttpClient, base_url: str = "https://www.okx.com") -> None:
        self._http = http
        self._base = f"{base_url.rstrip('/')}/api/v5/public"
        self._contract_values: dict[str, float] = {}

    def transform_query(self, query: LiquidationQuery) -> Mapping[str, str]:
        return {"instType": "SWAP", "uly": f"{query.symbol}-USDT", "state": "filled"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        inst_id = f"{params['uly']}-SWAP"
        if inst_id not in self._contract_values:
            raw = await self._http.get_json(
                f"{self._base}/instruments",
                provider=self.provider_name,
                params={"instType": "SWAP", "instId": inst_id},
            )
            value = _first_float(raw, "ctVal")
            if value is None:
                raise ProviderResponseError(self.provider_name, f"{inst_id}: no contract value")
            self._contract_values[inst_id] = value
        orders = await self._http.get_json(
            f"{self._base}/liquidation-orders", provider=self.provider_name, params=params
        )
        return self._contract_values[inst_id], orders

    def transform(self, query: LiquidationQuery, raw: Any) -> LiquidationSummary:
        contract_value, payload = raw
        try:
            details = payload["data"][0]["details"] if payload["data"] else []
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                self.provider_name, "unexpected liquidation payload"
            ) from exc
        items: list[Liquidation] = []
        for d in details:
            price, contracts, ts = as_float(d.get("bkPx")), as_float(d.get("sz")), d.get("ts")
            side = {"long": Side.LONG, "short": Side.SHORT}.get(d.get("posSide"))
            if price is None or contracts is None or side is None or ts is None:
                continue
            size = contracts * contract_value
            items.append(
                Liquidation(
                    position=side,
                    price=price,
                    size=round(size, 8),
                    notional_usd=round(size * price, 2),
                    at=datetime.fromtimestamp(int(ts) / 1000, tz=UTC),
                )
            )
        times = [i.at for i in items]
        return LiquidationSummary(
            symbol=query.symbol,
            exchange=self.provider_name,
            count=len(items),
            since=min(times, default=None),
            until=max(times, default=None),
            long_usd=round(sum(i.notional_usd for i in items if i.position is Side.LONG), 2),
            short_usd=round(sum(i.notional_usd for i in items if i.position is Side.SHORT), 2),
            largest=tuple(
                sorted(items, key=lambda i: i.notional_usd, reverse=True)[:LARGEST_LIQUIDATIONS]
            ),
            note=(
                f"The last {len(items)} liquidations of OKX's {query.symbol}-USDT perpetual only; "
                "other exchanges and margin types are not included."
            ),
        )


def _first_float(raw: Any, key: str) -> float | None:
    try:
        return as_float(raw["data"][0].get(key))
    except (KeyError, IndexError, TypeError):
        return None
