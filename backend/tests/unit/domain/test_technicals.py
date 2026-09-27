from collections.abc import Sequence
from datetime import date, timedelta

import pytest

from argus.domain.markets import Candle
from argus.domain.technicals import LevelKind, analyse, levels, rsi, sma

START = date(2025, 1, 1)


def bars(closes: Sequence[float], spread: float = 0.0) -> list[Candle]:
    return [
        Candle(day=START + timedelta(days=i), open=c, high=c + spread, low=c - spread, close=c)
        for i, c in enumerate(closes)
    ]


class TestIndicators:
    def test_sma_needs_enough_bars(self) -> None:
        assert sma([1, 2, 3], 2) == 2.5
        assert sma([1, 2], 3) is None

    def test_rsi_extremes_and_balance(self) -> None:
        assert rsi([float(i) for i in range(30)]) == 100
        assert rsi([float(30 - i) for i in range(30)]) == pytest.approx(0)
        assert rsi([1.0, 2.0] * 15) == pytest.approx(50, abs=5)
        assert rsi([1.0] * 30) == 50
        assert rsi([1.0] * 10) is None


class TestLevels:
    def test_repeated_turning_points_become_levels(self) -> None:
        # Oscillates between ~90 and ~110 three times, then settles at 100.
        wave = [100, 104, 108, 110, 108, 104, 100, 96, 92, 90, 92, 96]
        found = levels(bars(wave * 3 + [100] * 6), close=100)
        assert [(lv.kind, round(lv.price)) for lv in found] == [
            (LevelKind.RESISTANCE, 110),
            (LevelKind.SUPPORT, 90),
        ]
        assert all(lv.touches >= 2 for lv in found)
        assert found[0].distance_pct == pytest.approx(10)

    def test_single_touches_are_not_levels(self) -> None:
        assert levels(bars([float(i) for i in range(40)]), close=40) == ()


class TestAnalyse:
    def test_reading_on_long_history(self) -> None:
        closes = [100 + i * 0.1 for i in range(300)]
        t = analyse(bars(closes, spread=1))
        assert t is not None
        assert t.sessions == 300
        assert t.close == pytest.approx(129.9)
        assert t.sma_200 == pytest.approx(sum(closes[-200:]) / 200)
        assert t.high_52w == pytest.approx(130.9)  # last 252 sessions only
        assert t.low_52w == pytest.approx(100 + 48 * 0.1 - 1)
        assert any("pivot" in m for m in t.method)

    def test_short_history_leaves_long_indicators_empty(self) -> None:
        t = analyse(bars([10.0] * 30))
        assert t is not None
        assert (t.sma_20, t.sma_50, t.sma_200) == (10, None, None)

    def test_no_bars(self) -> None:
        assert analyse([]) is None
