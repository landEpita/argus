from datetime import UTC, datetime
from typing import Any

from argus.domain.markets import (
    FUNDING_RATES,
    QUOTE,
    WATCH_SET,
    FundingQuery,
    FundingRate,
    Quote,
    QuoteQuery,
)
from argus.infra.cache import InMemoryTTLCache
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderUnavailableError
from argus.providers.registry import ProviderRegistry
from argus.services.finance import FinanceService
from tests.fakes import FakeClock

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


class Quotes(Fetcher[QuoteQuery, Quote]):
    provider_name = "stub"

    def __init__(self, broken: set[str]) -> None:
        self.broken = broken
        self.calls: list[str] = []

    async def extract(self, params: Any) -> Any:
        return None

    def transform(self, query: QuoteQuery, raw: Any) -> Quote:
        self.calls.append(query.instrument.symbol)
        if query.instrument.symbol in self.broken:
            raise ProviderUnavailableError("stub", "HTTP 429")
        return Quote(instrument=query.instrument, price=1.0, as_of=NOW, source="stub")


async def test_one_bad_symbol_only_removes_itself() -> None:
    fetcher = Quotes({"^VIX"})
    registry = ProviderRegistry()
    registry.register(QUOTE, fetcher)
    service = FinanceService(registry, InMemoryTTLCache(clock=FakeClock()))
    board = await service.quotes()
    assert len(board.items) == len(WATCH_SET) - 1
    assert [m.key for m in board.missing] == ["^VIX"]
    await service.quotes()
    assert fetcher.calls.count("^GSPC") == 1  # cached


class Funding(Fetcher[FundingQuery, FundingRate]):
    provider_name = "stub"

    async def extract(self, params: Any) -> Any:
        return None

    def transform(self, query: FundingQuery, raw: Any) -> FundingRate:
        if query.symbol == "DOGE":
            raise ProviderUnavailableError("stub", "no market")
        return FundingRate(symbol=query.symbol, exchange="stub", rate=0.0001, annualized_pct=10.95)


async def test_funding_board_lists_missing_symbols() -> None:
    registry = ProviderRegistry()
    registry.register(FUNDING_RATES, Funding())
    board = await FinanceService(registry, InMemoryTTLCache()).funding(["BTC", "DOGE"])
    assert [r.symbol for r in board.items] == ["BTC"]
    assert [m.key for m in board.missing] == ["DOGE"]


def _candles(n: int) -> tuple[Any, ...]:
    from datetime import date, timedelta

    from argus.domain.markets import Candle

    start = date(2024, 9, 1)
    return tuple(
        Candle(day=start + timedelta(days=i), open=1, high=1, low=1, close=1.0 + i / 1000)
        for i in range(n)
    )


async def test_asset_trims_the_chart_but_not_the_reading() -> None:
    from argus.domain.markets import (
        PRICE_HISTORY,
        AssetClass,
        HistoryQuery,
        HistoryRange,
        Instrument,
        PriceHistory,
    )

    class History(Fetcher[HistoryQuery, PriceHistory]):
        provider_name = "stub"

        def __init__(self) -> None:
            self.ranges: list[str] = []

        async def extract(self, params: Any) -> Any:
            return None

        def transform(self, query: HistoryQuery, raw: Any) -> PriceHistory:
            self.ranges.append(query.range.value)
            return PriceHistory(
                instrument=Instrument(symbol="AAPL", name="Apple", asset_class=AssetClass.EQUITY),
                candles=_candles(730),
                source="stub",
            )

    fetcher = History()
    registry = ProviderRegistry()
    registry.register(PRICE_HISTORY, fetcher)
    service = FinanceService(registry, InMemoryTTLCache())
    month = await service.asset("AAPL", HistoryRange.MONTH)
    year = await service.asset("AAPL", HistoryRange.YEAR)
    assert len(month.history.candles) == 31
    assert 360 <= len(year.history.candles) <= 366
    assert month.technicals is not None
    assert month.technicals.sessions == 730
    assert month.technicals.sma_200 is not None
    assert fetcher.ranges == ["2y"]  # one fetch serves both ranges
    await service.asset("AAPL", HistoryRange.FIVE_YEARS)
    assert fetcher.ranges == ["2y", "5y"]


async def test_liquidations_and_energy_boards() -> None:
    from argus.domain.energy import ENERGY_SERIES, SERIES, EnergySeriesQuery, Reading
    from argus.domain.markets import LIQUIDATIONS, LiquidationQuery, LiquidationSummary

    class Liq(Fetcher[LiquidationQuery, LiquidationSummary]):
        provider_name = "stub"

        async def extract(self, params: Any) -> Any:
            return None

        def transform(self, query: LiquidationQuery, raw: Any) -> LiquidationSummary:
            if query.symbol == "XYZ":
                raise ProviderUnavailableError("stub", "no market")
            return LiquidationSummary(
                symbol=query.symbol, exchange="stub", count=0, since=None, until=None,
                long_usd=0, short_usd=0, largest=(), note="n",
            )  # fmt: skip

    class Energy(Fetcher[EnergySeriesQuery, list[Reading]]):
        provider_name = "stub"

        async def extract(self, params: Any) -> Any:
            return None

        def transform(self, query: EnergySeriesQuery, raw: Any) -> list[Reading]:
            if query.spec.id == "spr":
                raise ProviderUnavailableError("stub", "HTTP 429")
            if query.spec.id == "gasoline":
                return []
            return [Reading(period=NOW.date(), value=1.0)]

    registry = ProviderRegistry()
    registry.register(LIQUIDATIONS, Liq())
    registry.register(ENERGY_SERIES, Energy())
    service = FinanceService(registry, InMemoryTTLCache())
    liq = await service.liquidations(["BTC", "XYZ"])
    assert ([i.symbol for i in liq.items], [m.key for m in liq.missing]) == (["BTC"], ["XYZ"])
    energy = await service.energy_stocks()
    assert len(energy.items) == len(SERIES) - 2
    assert sorted(m.key for m in energy.missing) == ["gasoline", "spr"]
