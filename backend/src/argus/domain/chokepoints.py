"""
Maritime chokepoints: daily transits, compared with two baselines.

One baseline is never enough: after months of disruption the last 90 days are
already abnormal (Hormuz in 2026: ~9 ships a day over 90 days, ~90 a day a
year earlier). The same week last year is the headline comparison; the
90-day one shows whether things are still getting worse.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import GeoPoint


class DailyTransits(DomainModel):
    date: date
    total: int = Field(ge=0)
    tankers: int = Field(ge=0)


class ChokepointTraffic(DomainModel):
    id: str
    name: str
    position: GeoPoint
    latest_date: date = Field(description="PortWatch publishes with a delay of several days")
    last_7d_avg: float
    prior_90d_avg: float | None = None
    last_year_avg: float | None = Field(default=None, description="Same 7 days, one year earlier")
    change_vs_90d_pct: float | None = None
    change_vs_last_year_pct: float | None = None
    tanker_share_pct: float | None = None
    daily: tuple[DailyTransits, ...] = Field(description="Last 90 days, oldest first")
    source: str


class ChokepointQuery(DomainModel):
    pass


CHOKEPOINT_TRAFFIC: Capability[ChokepointQuery, list[ChokepointTraffic]] = Capability(
    "maritime.chokepoints", "Daily vessel transits through strategic chokepoints."
)


def summarise(
    id: str, name: str, position: GeoPoint, days: list[DailyTransits], source: str
) -> ChokepointTraffic | None:
    """Averages and changes from a daily series (any order, gaps allowed)."""
    if not days:
        return None
    series = sorted(days, key=lambda d: d.date)
    latest = series[-1].date
    by_date = {d.date: d for d in series}

    def avg(start_offset: int, end_offset: int) -> float | None:
        # Days in (latest - start_offset, latest - end_offset], inclusive of the end.
        values = [
            by_date[d].total
            for d in (
                date.fromordinal(latest.toordinal() - o) for o in range(end_offset, start_offset)
            )
            if d in by_date
        ]
        return sum(values) / len(values) if values else None

    last7 = avg(7, 0) or 0.0  # never None: the latest day is in the window
    prior90 = avg(97, 7)
    last_year = avg(372, 365)

    def change(base: float | None) -> float | None:
        return None if not base else round((last7 - base) / base * 100, 1)

    recent = [d for d in series if (latest - d.date).days < 7]
    total = sum(d.total for d in recent)
    return ChokepointTraffic(
        id=id,
        name=name,
        position=position,
        latest_date=latest,
        last_7d_avg=round(last7, 1),
        prior_90d_avg=None if prior90 is None else round(prior90, 1),
        last_year_avg=None if last_year is None else round(last_year, 1),
        change_vs_90d_pct=change(prior90),
        change_vs_last_year_pct=change(last_year),
        tanker_share_pct=round(sum(d.tankers for d in recent) / total * 100, 1) if total else None,
        daily=tuple(d for d in series if (latest - d.date).days < 90),
        source=source,
    )
