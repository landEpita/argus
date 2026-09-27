"""
Polymarket Gamma API (events and their markets), no key.

Access is blocked by law in some countries (France among them, by ISP DNS);
there it simply fails and the board says the source is unreachable. Argus
does not work around such blocks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, parse_utc
from argus.domain.markets import Outcome, PredictionMarket, PredictionQuery
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://gamma-api.polymarket.com"


def _json_list(value: Any) -> list[Any]:
    """Gamma encodes arrays as JSON strings ('["Yes", "No"]')."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


class PolymarketFetcher(Fetcher[PredictionQuery, list[PredictionMarket]]):
    provider_name = "polymarket"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/events"

    def transform_query(self, query: PredictionQuery) -> Mapping[str, str]:
        return {
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": str(query.limit),
            "tag_slug": query.tag,
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, params=params)

    def transform(self, query: PredictionQuery, raw: Any) -> list[PredictionMarket]:
        if not isinstance(raw, list):
            raise ProviderResponseError(self.provider_name, "expected a list of events")
        markets: list[PredictionMarket] = []
        for event in raw:
            for market in event.get("markets") or []:
                parsed = self._market(event, market)
                if parsed is not None:
                    markets.append(parsed)
        markets.sort(key=lambda m: m.volume_24h_usd or 0.0, reverse=True)
        return markets[: query.limit]

    def _market(self, event: Any, market: Any) -> PredictionMarket | None:
        if market.get("closed") or not market.get("active", True):
            return None  # resolved or halted: not a live probability
        labels = _json_list(market.get("outcomes"))
        prices = [as_float(p) for p in _json_list(market.get("outcomePrices"))]
        if not labels or len(labels) != len(prices) or any(p is None for p in prices):
            return None
        try:
            return PredictionMarket(
                id=str(market["id"]),
                question=market.get("question") or event.get("title") or "",
                event_title=event.get("title") or "",
                outcomes=tuple(
                    Outcome(label=str(label), probability=min(1.0, max(0.0, price or 0.0)))
                    for label, price in zip(labels, prices, strict=True)
                ),
                one_day_change=as_float(market.get("oneDayPriceChange")),
                volume_usd=as_float(market.get("volume")),
                volume_24h_usd=as_float(market.get("volume24hr")),
                end_date=parse_utc(market.get("endDate")),
                url=f"https://polymarket.com/event/{event.get('slug') or market.get('slug')}",
                source=self.provider_name,
            )
        except (KeyError, TypeError, ValidationError):
            return None
