"""
OpenBB Platform as an optional quote provider (``pip install argus-backend[openbb]``).

OpenBB is a large dependency, so it is never imported unless enabled, and the
adapter talks to a tiny ``HistoryLoader`` callable rather than to ``obb``
directly: tests pass a fake, and the composition root builds the real one.
Its yfinance provider impersonates a browser, which gets through when Yahoo's
plain chart API is rate-limiting us — a useful fallback, even if the data is
ultimately the same.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from argus.adapters.finance.yahoo import quote_from_closes
from argus.domain.markets import Quote, QuoteQuery
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError

# symbol, start date -> [(date, close), …] oldest first
HistoryLoader = Callable[[str, date], Awaitable[list[tuple[date, float]]]]


def openbb_history_loader(provider: str = "yfinance") -> HistoryLoader:
    """The real loader. Raises ImportError when OpenBB is not installed."""
    from openbb import obb  # type: ignore[import-not-found]  # optional extra

    def load_sync(symbol: str, start: date) -> list[tuple[date, float]]:
        result = obb.equity.price.historical(symbol=symbol, start_date=start, provider=provider)
        return [(row.date, float(row.close)) for row in result.results]

    async def load(symbol: str, start: date) -> list[tuple[date, float]]:
        return await asyncio.to_thread(load_sync, symbol, start)  # OpenBB is synchronous

    return load


class OpenBBQuoteFetcher(Fetcher[QuoteQuery, Quote]):
    provider_name = "openbb"

    def __init__(self, load: HistoryLoader, lookback_days: int = 60) -> None:
        self._load = load
        self._lookback = timedelta(days=lookback_days)

    def transform_query(self, query: QuoteQuery) -> Mapping[str, str]:
        start = datetime.now(UTC).date() - self._lookback
        return {"symbol": query.instrument.symbol, "start": start.isoformat()}

    async def extract(self, params: Mapping[str, str]) -> Any:
        try:
            return await self._load(params["symbol"], date.fromisoformat(params["start"]))
        except Exception as exc:  # OpenBB raises its own exception zoo
            raise ProviderUnavailableError(
                self.provider_name, f"{type(exc).__name__}: {exc}"
            ) from exc

    def transform(self, query: QuoteQuery, raw: Any) -> Quote:
        rows = sorted(raw or [], key=lambda r: r[0])
        if not rows:
            raise ProviderResponseError(self.provider_name, f"{query.instrument.symbol}: no data")
        last_day, last_close = rows[-1]
        return quote_from_closes(
            query.instrument,
            price=last_close,
            closes=[c for _, c in rows],
            previous=rows[-2][1] if len(rows) >= 2 else None,
            at=datetime.combine(last_day, datetime.min.time(), tzinfo=UTC),
            currency=None,
            source=self.provider_name,
        )
