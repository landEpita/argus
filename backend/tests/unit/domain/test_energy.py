from datetime import date, timedelta

import pytest

from argus.domain.energy import SERIES, Reading, summarise

CRUDE = SERIES[0]
LATEST = date(2026, 9, 18)


def weekly(values: dict[date, float]) -> list[Reading]:
    return [Reading(period=d, value=v) for d, v in values.items()]


def test_compares_with_the_same_week_of_five_years() -> None:
    # Weekly readings: 100 in every previous year, 120 now.
    readings = {LATEST - timedelta(weeks=w): 100.0 for w in range(1, 320)}
    readings[LATEST] = 120.0
    stock = summarise(CRUDE, weekly(readings), source="eia")
    assert stock is not None
    assert stock.latest.value == 120
    assert stock.week_change == 20
    assert stock.five_year_avg == 100
    assert stock.vs_five_year_pct == pytest.approx(20)
    assert len(stock.history) == 52
    assert stock.history[-1].period == LATEST
    assert stock.unit == "thousand bbl"


def test_missing_years_are_left_out() -> None:
    stock = summarise(CRUDE, weekly({LATEST: 110.0, date(2025, 9, 19): 100.0}), source="eia")
    assert stock is not None
    assert stock.five_year_avg == 100
    assert (stock.five_year_min, stock.five_year_max) == (100, 100)


def test_short_or_empty_series() -> None:
    lone = summarise(CRUDE, weekly({LATEST: 1.0}), source="eia")
    assert lone is not None
    assert (lone.week_change, lone.five_year_avg, lone.vs_five_year_pct) == (None, None, None)
    assert summarise(CRUDE, [], source="eia") is None


def test_leap_day_goes_back_to_the_28th() -> None:
    leap = date(2028, 2, 29)
    stock = summarise(CRUDE, weekly({leap: 2.0, date(2027, 2, 28): 1.0}), source="eia")
    assert stock is not None
    assert stock.five_year_avg == 1
