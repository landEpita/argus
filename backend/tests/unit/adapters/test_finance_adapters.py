import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.finance.crypto import (
    BinanceFundingFetcher,
    CoinGeckoMarketsFetcher,
    OkxFundingFetcher,
)
from argus.adapters.finance.macro import (
    CryptoFearGreedFetcher,
    ForexFactoryCalendarFetcher,
    TreasuryYieldFetcher,
)
from argus.adapters.finance.openbb import OpenBBQuoteFetcher
from argus.adapters.finance.polymarket import PolymarketFetcher, _json_list
from argus.adapters.finance.portwatch import PortWatchFetcher, _date
from argus.adapters.finance.yahoo import YahooQuoteFetcher
from argus.domain.chokepoints import DailyTransits, summarise
from argus.domain.geo import GeoPoint
from argus.domain.macro import EmptyQuery, Impact
from argus.domain.markets import WATCH_SET, CryptoQuery, FundingQuery, PredictionQuery, QuoteQuery
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.fakes import FakeWallClock, StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"
NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
SPX = next(i for i in WATCH_SET if i.symbol == "^GSPC")
WTI = next(i for i in WATCH_SET if i.symbol == "CL=F")


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


class TestYahoo:
    async def test_quote_from_chart(self) -> None:
        raw = load("yahoo_chart_gspc.json")
        http = StubHttp(raw)
        quote = await YahooQuoteFetcher(http, "https://y.test/chart").fetch(
            QuoteQuery(instrument=SPX)
        )
        url, params = http.calls[0]
        assert url == "https://y.test/chart/^GSPC"
        assert params == {"range": "3mo", "interval": "1d"}
        closes = [
            c for c in raw["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None
        ]
        assert quote.price == raw["chart"]["result"][0]["meta"]["regularMarketPrice"]
        assert quote.previous_close == pytest.approx(closes[-2])
        assert quote.change_pct == pytest.approx(
            (quote.price - closes[-2]) / closes[-2] * 100, abs=1e-3
        )
        assert quote.currency == "USD"
        assert quote.as_of.tzinfo is not None
        assert quote.delayed is True
        assert len(quote.history) <= 30

    async def test_commodity_history(self) -> None:
        quote = await YahooQuoteFetcher(StubHttp(load("yahoo_chart_cl.json"))).fetch(
            QuoteQuery(instrument=WTI)
        )
        assert quote.instrument.unit == "USD/bbl"
        assert len(quote.history) > 5

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            {"chart": {"result": []}},
            {"chart": {"result": [{"meta": {}, "indicators": {"quote": [{"close": []}]}}]}},
        ],
    )
    def test_bad_payloads(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            YahooQuoteFetcher(StubHttp()).transform(QuoteQuery(instrument=SPX), raw)


class TestOpenBB:
    async def test_uses_the_injected_loader(self) -> None:
        seen: list[tuple[str, date]] = []

        async def loader(symbol: str, start: date) -> list[tuple[date, float]]:
            seen.append((symbol, start))
            return [
                (date(2026, 9, 25), 100.0),
                (date(2026, 9, 24), 98.0),
                (date(2026, 9, 26), 101.0),
            ]

        quote = await OpenBBQuoteFetcher(loader).fetch(QuoteQuery(instrument=SPX))
        assert seen[0][0] == "^GSPC"
        assert quote.price == 101.0
        assert quote.previous_close == 100.0
        assert quote.history == (98.0, 100.0, 101.0)
        assert quote.source == "openbb"

    async def test_loader_errors_become_unavailable(self) -> None:
        async def loader(symbol: str, start: date) -> list[tuple[date, float]]:
            raise RuntimeError("yfinance exploded")

        with pytest.raises(ProviderUnavailableError, match="RuntimeError"):
            await OpenBBQuoteFetcher(loader).fetch(QuoteQuery(instrument=SPX))

    async def test_empty_history(self) -> None:
        async def loader(symbol: str, start: date) -> list[tuple[date, float]]:
            return []

        with pytest.raises(ProviderResponseError, match="no data"):
            await OpenBBQuoteFetcher(loader).fetch(QuoteQuery(instrument=SPX))


class TestCrypto:
    async def test_coingecko(self) -> None:
        http = StubHttp(load("coingecko_markets.json"))
        assets = await CoinGeckoMarketsFetcher(http, "https://cg.test/api/v3").fetch(
            CryptoQuery(limit=4)
        )
        assert http.calls[0][0] == "https://cg.test/api/v3/coins/markets"
        assert http.calls[0][1]["per_page"] == "4"
        assert assets[0].symbol == "BTC"
        assert assets[0].price_usd > 0
        assert assets[0].updated_at is not None

    def test_coingecko_bad(self) -> None:
        with pytest.raises(ProviderResponseError):
            CoinGeckoMarketsFetcher(StubHttp()).transform(CryptoQuery(), {"status": "rate limited"})
        assert (
            CoinGeckoMarketsFetcher(StubHttp()).transform(
                CryptoQuery(), [{"id": "x", "current_price": None}]
            )
            == []
        )

    async def test_binance_funding(self) -> None:
        http = StubHttp(load("binance_premium_index.json"))
        rate = await BinanceFundingFetcher(http).fetch(FundingQuery(symbol="BTC"))
        assert http.calls[0][1] == {"symbol": "BTCUSDT"}
        assert rate.rate == pytest.approx(0.00000944)
        assert rate.annualized_pct == pytest.approx(0.00000944 * 1095 * 100, abs=0.01)
        assert rate.next_funding_at is not None

    async def test_okx_funding(self) -> None:
        http = StubHttp(load("okx_funding_rate.json"))
        rate = await OkxFundingFetcher(http).fetch(FundingQuery(symbol="BTC"))
        assert http.calls[0][1] == {"instId": "BTC-USDT-SWAP"}
        assert rate.exchange == "okx"

    @pytest.mark.parametrize("raw", [{}, {"lastFundingRate": "x"}])
    def test_binance_bad(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            BinanceFundingFetcher(StubHttp()).transform(FundingQuery(symbol="BTC"), raw)

    @pytest.mark.parametrize("raw", [{}, {"data": []}, {"data": [{"fundingRate": ""}]}])
    def test_okx_bad(self, raw: Any) -> None:
        with pytest.raises(ProviderResponseError):
            OkxFundingFetcher(StubHttp()).transform(FundingQuery(symbol="BTC"), raw)


class TestPolymarket:
    async def test_live_markets_only_with_probabilities(self) -> None:
        http = StubHttp(load("polymarket_events.json"))
        markets = await PolymarketFetcher(http).fetch(PredictionQuery(limit=10))
        assert http.calls[0][1]["tag_slug"] == "geopolitics"
        assert markets  # closed markets in the fixture are dropped
        assert all(len(m.outcomes) == 2 for m in markets)
        assert all(0 <= o.probability <= 1 for m in markets for o in m.outcomes)
        assert all(m.url.startswith("https://polymarket.com/event/") for m in markets)
        assert "Hormuz" in " ".join(m.event_title for m in markets)

    def test_json_list(self) -> None:
        assert _json_list('["Yes", "No"]') == ["Yes", "No"]
        assert _json_list(["a"]) == ["a"]
        assert _json_list("nope") == []
        assert _json_list('{"a": 1}') == []
        assert _json_list(None) == []

    def test_mismatched_outcomes_are_skipped(self) -> None:
        raw = [
            {
                "title": "E",
                "slug": "e",
                "markets": [{"id": 1, "outcomes": '["Yes","No"]', "outcomePrices": '["0.5"]'}],
            }
        ]
        assert PolymarketFetcher(StubHttp()).transform(PredictionQuery(), raw) == []

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            PolymarketFetcher(StubHttp()).transform(PredictionQuery(), {"error": "x"})


class TestMacro:
    async def test_crypto_fear_greed(self) -> None:
        [index] = await CryptoFearGreedFetcher(StubHttp(load("fear_greed_crypto.json"))).fetch(
            EmptyQuery()
        )
        assert index.latest.value == 70
        assert index.latest.label == "Greed"
        assert index.history[0] == index.latest

    def test_fear_greed_empty(self) -> None:
        with pytest.raises(ProviderResponseError):
            CryptoFearGreedFetcher(StubHttp()).transform(EmptyQuery(), {"data": []})

    async def test_treasury_curve(self) -> None:
        http = StubHttp((FIXTURES / "treasury_yields.csv").read_bytes())
        curve = await TreasuryYieldFetcher(http, clock=FakeWallClock(NOW)).fetch(EmptyQuery())
        assert http.calls[0][0].endswith("/daily-treasury-rates.csv/2026/all")
        assert curve.date == date(2026, 9, 25)
        assert [p.tenor for p in curve.points][:2] == ["1 Mo", "1.5 Month"]
        assert curve.points == tuple(sorted(curve.points, key=lambda p: p.years))
        ten = next(p for p in curve.points if p.tenor == "10 Yr")
        assert ten.rate_pct == 5.17
        assert curve.inverted_2y_10y is False
        assert curve.previous

    @pytest.mark.parametrize("raw", [b"", b"<html>", b"Date,1 Mo\nnot-a-date,4\n"])
    def test_treasury_bad(self, raw: bytes) -> None:
        with pytest.raises(ProviderResponseError):
            TreasuryYieldFetcher(StubHttp(), clock=FakeWallClock(NOW)).transform(EmptyQuery(), raw)

    async def test_calendar(self) -> None:
        events = await ForexFactoryCalendarFetcher(StubHttp(load("ff_calendar.json"))).fetch(
            EmptyQuery()
        )
        assert len(events) == 6
        assert events == sorted(events, key=lambda e: e.at)
        assert {e.impact for e in events} == {Impact.HIGH, Impact.LOW, Impact.HOLIDAY}
        assert all(e.at.utcoffset() == timedelta(0) for e in events)

    def test_calendar_bad(self) -> None:
        with pytest.raises(ProviderResponseError):
            ForexFactoryCalendarFetcher(StubHttp()).transform(EmptyQuery(), {})


class TestChokepoints:
    def test_summary_compares_with_last_year_and_90_days(self) -> None:
        raw = load("portwatch_daily_hormuz.json")
        days = [
            DailyTransits(
                date=date.fromisoformat(f["attributes"]["date"]),
                total=f["attributes"]["n_total"],
                tankers=f["attributes"]["n_tanker"],
            )
            for f in raw["features"]
        ]
        s = summarise(
            "chokepoint6", "Strait of Hormuz", GeoPoint(lat=26.5, lon=56.3), days, "portwatch"
        )
        assert s is not None
        assert s.latest_date == date(2026, 9, 20)
        assert s.last_7d_avg == pytest.approx(3.1, abs=0.1)
        assert s.last_year_avg is not None
        assert s.last_year_avg > 50
        assert s.change_vs_last_year_pct is not None
        assert s.change_vs_last_year_pct < -90
        assert s.prior_90d_avg == pytest.approx(9.5, abs=0.1)
        assert len(s.daily) == 90

    def test_no_baseline_means_no_change(self) -> None:
        days = [DailyTransits(date=date(2026, 9, d), total=10, tankers=5) for d in range(1, 5)]
        s = summarise("x", "X", GeoPoint(lat=0, lon=0), days, "t")
        assert s is not None
        assert s.change_vs_last_year_pct is None
        assert s.tanker_share_pct == 50.0
        assert summarise("x", "X", GeoPoint(lat=0, lon=0), [], "t") is None

    async def test_fetch_pages_and_joins(self) -> None:
        cps, daily = load("portwatch_chokepoints.json"), load("portwatch_daily_hormuz.json")
        http = StubHttp(lambda url: cps if "chokepoints_database" in url else daily)
        items = await PortWatchFetcher(http, clock=FakeWallClock(NOW)).fetch(
            __import__("argus.domain.chokepoints", fromlist=["x"]).ChokepointQuery()
        )
        assert [c.name for c in items] == ["Strait of Hormuz"]  # only it has daily data here
        daily_call = next(p for u, p in http.calls if "Daily" in u)
        assert daily_call["where"] == "date >= DATE '2025-09-12'"

    def test_arcgis_dates(self) -> None:
        assert _date("2026-09-20") == date(2026, 9, 20)
        assert _date(1790380800000) == date(2026, 9, 26)
        assert _date("junk") is None
        assert _date(None) is None

    def test_bad_payload(self) -> None:
        from argus.domain.chokepoints import ChokepointQuery

        with pytest.raises(ProviderResponseError):
            PortWatchFetcher(StubHttp(), clock=FakeWallClock(NOW)).transform(
                ChokepointQuery(), {"daily": []}
            )

    async def test_daily_without_features_is_an_error(self) -> None:
        from argus.domain.chokepoints import ChokepointQuery

        def respond(url: str) -> dict[str, Any]:
            return {"features": []} if "chokepoints_database" in url else {"error": "x"}

        http = StubHttp(respond)
        with pytest.raises(ProviderResponseError, match="no features"):
            await PortWatchFetcher(http, clock=FakeWallClock(NOW)).fetch(ChokepointQuery())


def test_previous_close_is_dated_not_positional() -> None:
    # Friday's price; Thursday's bar is missing (null): yesterday is Wednesday, and
    # the positional rule would wrongly pick Tuesday.
    day = 86400
    friday = 1790380800 - day  # 2026-09-25 00:00 UTC
    raw = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 110.0,
                        "regularMarketTime": friday + 72000,
                        "gmtoffset": 0,
                    },
                    "timestamp": [friday - 3 * day, friday - 2 * day, friday - day, friday],
                    "indicators": {"quote": [{"close": [90.0, 100.0, None, 110.0]}]},
                }
            ]
        }
    }
    quote = YahooQuoteFetcher(StubHttp()).transform(QuoteQuery(instrument=WTI), raw)
    assert quote.previous_close == 100.0
    assert quote.change_pct == 10.0
    assert quote.history == (90.0, 100.0, 110.0)


class TestHistoryAndDerivatives:
    async def test_yahoo_history_for_any_symbol(self) -> None:
        from argus.adapters.finance.yahoo import YahooHistoryFetcher
        from argus.domain.markets import AssetClass, HistoryQuery, HistoryRange

        http = StubHttp(load("yahoo_history_aapl.json"))
        history = await YahooHistoryFetcher(http, "https://y.test/chart").fetch(
            HistoryQuery(symbol="AAPL", range=HistoryRange.YEAR)
        )
        assert http.calls[0] == ("https://y.test/chart/AAPL", {"range": "1y", "interval": "1d"})
        assert history.instrument.name == "Apple Inc."
        assert history.instrument.asset_class is AssetClass.EQUITY
        assert history.currency == "USD"
        assert len(history.candles) > 200
        days = [c.day for c in history.candles]
        assert days == sorted(days)
        assert all(c.low <= c.close <= c.high for c in history.candles)
        assert all(c.volume is None or c.volume > 0 for c in history.candles)

    async def test_watch_set_symbols_keep_their_curated_names(self) -> None:
        from argus.adapters.finance.yahoo import YahooHistoryFetcher
        from argus.domain.markets import HistoryQuery

        history = await YahooHistoryFetcher(StubHttp(load("yahoo_chart_cl.json"))).fetch(
            HistoryQuery(symbol="CL=F")
        )
        assert history.instrument == WTI

    async def test_yahoo_history_rejects_odd_payloads(self) -> None:
        from argus.adapters.finance.yahoo import YahooHistoryFetcher
        from argus.domain.markets import HistoryQuery

        with pytest.raises(ProviderResponseError):
            await YahooHistoryFetcher(StubHttp({"chart": {"result": []}})).fetch(
                HistoryQuery(symbol="AAPL")
            )

    async def test_okx_liquidations_in_base_units(self) -> None:
        from argus.adapters.finance.crypto import OkxLiquidationFetcher
        from argus.domain.markets import LiquidationQuery, Side

        def payload(url: str) -> Any:
            if url.endswith("/instruments"):
                return load("okx_instrument_btc.json")
            return load("okx_liquidations_btc.json")

        http = StubHttp(payload)
        fetcher = OkxLiquidationFetcher(http, "https://okx.test")
        summary = await fetcher.fetch(LiquidationQuery(symbol="BTC"))
        raw = load("okx_liquidations_btc.json")["data"][0]["details"]
        assert summary.count == len(raw) == 100
        total = sum(float(d["sz"]) * 0.01 * float(d["bkPx"]) for d in raw)
        assert summary.long_usd + summary.short_usd == pytest.approx(total, rel=1e-6)
        assert summary.largest[0].notional_usd >= summary.largest[-1].notional_usd
        assert summary.since is not None
        assert summary.until is not None
        assert summary.since <= summary.until
        assert "OKX" in summary.note
        assert {liq.position for liq in summary.largest} <= {Side.LONG, Side.SHORT}
        # The contract value is fetched once.
        await fetcher.fetch(LiquidationQuery(symbol="BTC"))
        assert [u for u, _ in http.calls].count("https://okx.test/api/v5/public/instruments") == 1

    async def test_okx_liquidations_without_contract_value(self) -> None:
        from argus.adapters.finance.crypto import OkxLiquidationFetcher
        from argus.domain.markets import LiquidationQuery

        with pytest.raises(ProviderResponseError):
            await OkxLiquidationFetcher(StubHttp({"data": []})).fetch(
                LiquidationQuery(symbol="BTC")
            )

    async def test_okx_no_recent_liquidations(self) -> None:
        from argus.adapters.finance.crypto import OkxLiquidationFetcher
        from argus.domain.markets import LiquidationQuery

        def payload(url: str) -> Any:
            return {"data": [{"ctVal": "0.01"}]} if url.endswith("/instruments") else {"data": []}

        summary = await OkxLiquidationFetcher(StubHttp(payload)).fetch(
            LiquidationQuery(symbol="BTC")
        )
        assert (summary.count, summary.since, summary.long_usd) == (0, None, 0)

    async def test_eia_series(self) -> None:
        from argus.adapters.finance.eia import EiaSeriesFetcher
        from argus.domain.energy import SERIES, EnergySeriesQuery, summarise

        http = StubHttp(load("eia_crude_stocks.json"))
        readings = await EiaSeriesFetcher(http, "KEY", "https://eia.test/v2/seriesid").fetch(
            EnergySeriesQuery(spec=SERIES[0])
        )
        assert http.calls[0] == (
            "https://eia.test/v2/seriesid/PET.WCESTUS1.W",
            {"api_key": "KEY", "length": "320"},
        )
        assert len(readings) == 320
        stock = summarise(SERIES[0], readings, source="eia")
        assert stock is not None
        assert stock.latest.period == date(2026, 9, 18)
        assert stock.latest.value == 426398
        assert stock.five_year_avg is not None
        assert stock.vs_five_year_pct is not None

    async def test_eia_gas_storage_and_errors(self) -> None:
        from argus.adapters.finance.eia import EiaSeriesFetcher
        from argus.domain.energy import SERIES, EnergySeriesQuery

        gas = next(s for s in SERIES if s.id == "natural_gas")
        readings = await EiaSeriesFetcher(StubHttp(load("eia_gas_storage.json")), "K").fetch(
            EnergySeriesQuery(spec=gas)
        )
        assert readings[0].value == 3351
        for bad in ({"error": "invalid key"}, {"response": {"data": [{"period": "x"}]}}):
            with pytest.raises(ProviderResponseError):
                await EiaSeriesFetcher(StubHttp(bad), "K").fetch(EnergySeriesQuery(spec=gas))


async def test_yahoo_quote_carries_the_session_range() -> None:
    raw = load("yahoo_chart_gspc.json")
    meta = raw["chart"]["result"][0]["meta"]
    quote = await YahooQuoteFetcher(StubHttp(raw)).fetch(QuoteQuery(instrument=SPX))
    assert quote.day_low == meta["regularMarketDayLow"]
    assert quote.day_high == meta["regularMarketDayHigh"]
    assert quote.day_low is not None
    assert quote.day_high is not None
    assert quote.day_low <= quote.price <= quote.day_high
