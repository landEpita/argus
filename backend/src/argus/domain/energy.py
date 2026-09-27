"""
Weekly US energy inventories (EIA), compared with the five-year average.

Units stay those of the source (thousand barrels, billion cubic feet): they
are how the market reads these numbers, and the unit travels with the value.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability

HISTORY_WEEKS = 52
FIVE_YEARS = 5
# Weekly readings sit at most 3.5 days from any date.
SAME_WEEK_TOLERANCE = timedelta(days=4)


class EnergySeriesSpec(DomainModel):
    id: str
    name: str
    unit: str
    eia_series: str


SERIES: tuple[EnergySeriesSpec, ...] = (
    EnergySeriesSpec(
        id="crude", name="US crude oil (ex. SPR)", unit="thousand bbl", eia_series="PET.WCESTUS1.W"
    ),
    EnergySeriesSpec(
        id="spr",
        name="Strategic Petroleum Reserve",
        unit="thousand bbl",
        eia_series="PET.WCSSTUS1.W",
    ),
    EnergySeriesSpec(
        id="gasoline", name="US gasoline", unit="thousand bbl", eia_series="PET.WGTSTUS1.W"
    ),
    EnergySeriesSpec(
        id="distillate", name="US distillates", unit="thousand bbl", eia_series="PET.WDISTUS1.W"
    ),
    EnergySeriesSpec(
        id="natural_gas",
        name="US natural gas in storage (Lower 48)",
        unit="Bcf",
        eia_series="NG.NW2_EPG0_SWO_R48_BCF.W",
    ),
)


class Reading(DomainModel):
    period: date = Field(description="Week ending")
    value: float


class EnergySeriesQuery(DomainModel):
    spec: EnergySeriesSpec


class EnergyStock(DomainModel):
    id: str
    name: str
    unit: str
    latest: Reading
    week_change: float | None
    five_year_avg: float | None = Field(description="Same week of the 5 previous years")
    vs_five_year_pct: float | None
    five_year_min: float | None
    five_year_max: float | None
    history: tuple[Reading, ...] = Field(description=f"Last {HISTORY_WEEKS} weeks, oldest first")
    source: str


ENERGY_SERIES: Capability[EnergySeriesQuery, list[Reading]] = Capability(
    "energy.inventory_series", "Weekly readings of one inventory series, newest first."
)


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _same_week(readings: Sequence[Reading], target: date) -> Reading | None:
    best = min(readings, key=lambda r: abs(r.period - target), default=None)
    if best is None or abs(best.period - target) > SAME_WEEK_TOLERANCE:
        return None
    return best


def summarise(
    spec: EnergySeriesSpec, readings: Sequence[Reading], source: str
) -> EnergyStock | None:
    """None when the series is empty. Years with no matching week are left out."""
    ordered = sorted(readings, key=lambda r: r.period)
    if not ordered:
        return None
    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    past = [
        r
        for k in range(1, FIVE_YEARS + 1)
        if (r := _same_week(ordered, _years_back(latest.period, k))) is not None
    ]
    avg = sum(r.value for r in past) / len(past) if past else None
    return EnergyStock(
        id=spec.id,
        name=spec.name,
        unit=spec.unit,
        latest=latest,
        week_change=None if previous is None else latest.value - previous.value,
        five_year_avg=None if avg is None else round(avg, 1),
        vs_five_year_pct=None if not avg else round((latest.value - avg) / avg * 100, 2),
        five_year_min=min((r.value for r in past), default=None),
        five_year_max=max((r.value for r in past), default=None),
        history=tuple(ordered[-HISTORY_WEEKS:]),
        source=source,
    )
