"""
Country Signal Index — how much disruptive activity the feeds report *now*.

It is not a measure of structural stability or of risk: a country can be
fragile and quiet in the feeds, or stable and loud (an earthquake, a big news
day). Every point is traceable: each component keeps its raw count, the rule
that turned it into points, and the points themselves.

Components and their maximum points (sum = 100):

| component          | input                                              | max |
|--------------------|----------------------------------------------------|-----|
| reported_violence  | GDELT violent events, weighted 0.25 + 0.75·severity | 35  |
| news_attention     | stories mentioning the country, weighted by outlets | 20  |
| air_alerts         | regions under an active air-raid alert             | 15  |
| internet_outages   | worst ongoing outage severity                      | 15  |
| natural_hazards    | worst GDACS alert or M5+ earthquake                | 15  |

Counts are log-scaled so a flood of reports saturates instead of dominating.

Volume bias, and how it is corrected: GDELT and news attention measure how
much *English-language media* write about a country, so the United Kingdom
or India score high on an ordinary day. Once a country has a week-long
baseline (at least ``MIN_BASELINE_SAMPLES`` hourly snapshots), those two
components switch to *relative* mode — points for activity above that
country's usual level — and every component says which mode it used.
Single-source GDELT events weigh 0.3 instead of 1.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.events import EventCategory, GeoEvent
from argus.domain.news import Story

MIN_BASELINE_SAMPLES = 24
SINGLE_SOURCE_WEIGHT = 0.3
RELATIVE_FULL_AT = 3.0  # standard deviations above the usual level for full points


class Component(StrEnum):
    REPORTED_VIOLENCE = "reported_violence"
    NEWS_ATTENTION = "news_attention"
    AIR_ALERTS = "air_alerts"
    INTERNET_OUTAGES = "internet_outages"
    NATURAL_HAZARDS = "natural_hazards"


@dataclass(frozen=True, slots=True)
class Rule:
    max_points: float
    description: str
    saturation: float | None = None  # log scaling: this raw value gives full points
    volume_biased: bool = False  # switch to relative mode once a baseline exists


RULES: dict[Component, Rule] = {
    Component.REPORTED_VIOLENCE: Rule(
        35,
        "violent events reported by GDELT, weighted by severity and by number of sources",
        saturation=50,
        volume_biased=True,
    ),
    Component.NEWS_ATTENTION: Rule(
        20,
        "stories mentioning the country, each counted once per outlet",
        saturation=100,
        volume_biased=True,
    ),
    Component.AIR_ALERTS: Rule(15, "regions under an active air-raid alert (5 = full)"),
    Component.INTERNET_OUTAGES: Rule(15, "severity of the worst ongoing Internet outage"),
    Component.NATURAL_HAZARDS: Rule(15, "worst GDACS alert level or M5+ earthquake"),
}

HAZARD_CATEGORIES = frozenset(
    {
        EventCategory.EARTHQUAKE,
        EventCategory.TROPICAL_CYCLONE,
        EventCategory.FLOOD,
        EventCategory.VOLCANO,
        EventCategory.DROUGHT,
        EventCategory.WILDFIRE,
        EventCategory.TSUNAMI,
    }
)


class ScoreMode(StrEnum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class Baseline(DomainModel):
    mean: float
    std: float
    samples: int


class ComponentScore(DomainModel):
    component: Component
    raw: float = Field(description="The input count or level, before scaling")
    points: float = Field(ge=0)
    max_points: float
    rule: str
    mode: ScoreMode = ScoreMode.ABSOLUTE
    baseline_mean: float | None = Field(default=None, description="Usual raw value (relative mode)")
    evidence: tuple[str, ...] = Field(default=(), description="Ids of the items counted")


class CountrySignal(DomainModel):
    iso2: str
    name: str
    score: float = Field(ge=0, le=100)
    components: tuple[ComponentScore, ...]
    computed_at: datetime
    has_baseline: bool = Field(
        default=False, description="Volume-biased components are relative to the usual level"
    )


Baselines = dict[str, dict[Component, Baseline]]


def baselines_from(samples: Iterable[tuple[str, dict[Component, float]]]) -> Baselines:
    """Mean and standard deviation of each component's raw value, per country."""
    values: dict[str, dict[Component, list[float]]] = defaultdict(lambda: defaultdict(list))
    for iso2, raw in samples:
        for component, value in raw.items():
            values[iso2][component].append(value)
    result: Baselines = {}
    for iso2, by_component in values.items():
        result[iso2] = {}
        for component, xs in by_component.items():
            mean = sum(xs) / len(xs)
            variance = sum((x - mean) ** 2 for x in xs) / len(xs)
            result[iso2][component] = Baseline(mean=mean, std=math.sqrt(variance), samples=len(xs))
    return result


def _log_scaled(raw: float, saturation: float) -> float:
    return min(1.0, math.log1p(raw) / math.log1p(saturation)) if raw > 0 else 0.0


@dataclass
class _Tally:
    raw: float = 0.0
    evidence: list[str] | None = None

    def add(self, item_id: str) -> None:
        if self.evidence is None:
            self.evidence = []
        if len(self.evidence) < 20:
            self.evidence.append(item_id)


def _country(event: GeoEvent) -> str | None:
    value = event.details.get("country_iso2")
    return value if isinstance(value, str) else None


def compute(
    *,
    violence: Iterable[GeoEvent],
    air_alerts: Iterable[GeoEvent],
    outages: Iterable[GeoEvent],
    disasters: Iterable[GeoEvent],
    earthquakes: Iterable[GeoEvent],
    stories: Sequence[Story],
    names: dict[str, str],
    at: datetime,
    baselines: Baselines | None = None,
) -> list[CountrySignal]:
    """Scores for every country with at least one signal, highest first."""
    tallies: dict[str, dict[Component, _Tally]] = defaultdict(lambda: defaultdict(_Tally))

    for e in violence:
        if (code := _country(e)) is not None:
            t = tallies[code][Component.REPORTED_VIOLENCE]
            sources = e.details.get("num_sources")
            coverage = 1.0 if isinstance(sources, int) and sources >= 2 else SINGLE_SOURCE_WEIGHT
            t.raw += (0.25 + 0.75 * (e.severity or 0.0)) * coverage
            t.add(e.id)
    for e in air_alerts:
        if (code := _country(e)) is not None:
            t = tallies[code][Component.AIR_ALERTS]
            t.raw += 1
            t.add(e.id)
    for e in outages:
        if (code := _country(e)) is not None and e.details.get("ongoing") is True:
            t = tallies[code][Component.INTERNET_OUTAGES]
            t.raw = max(t.raw, e.severity or 0.0)
            t.add(e.id)
    for e in disasters:
        if (code := _country(e)) is not None and e.category in HAZARD_CATEGORIES:
            t = tallies[code][Component.NATURAL_HAZARDS]
            t.raw = max(t.raw, e.severity or 0.0)
            t.add(e.id)
    for e in earthquakes:
        magnitude = e.magnitude or 0.0
        if (code := _country(e)) is not None and magnitude >= 5:
            t = tallies[code][Component.NATURAL_HAZARDS]
            t.raw = max(t.raw, min(1.0, (magnitude - 5) / 3))  # M5 -> 0, M8 -> 1
            t.add(e.id)
    for story in stories:
        for code in story.countries:
            t = tallies[code][Component.NEWS_ATTENTION]
            t.raw += len(story.sources)
            t.add(story.id)

    results: list[CountrySignal] = []
    for code, by_component in tallies.items():
        if code not in names:
            continue
        country_baselines = (baselines or {}).get(code, {})
        scores: list[ComponentScore] = []
        used_baseline = False
        for component, rule in RULES.items():
            tally = by_component.get(component)
            raw = tally.raw if tally else 0.0
            baseline = country_baselines.get(component)
            relative = (
                rule.volume_biased
                and baseline is not None
                and baseline.samples >= MIN_BASELINE_SAMPLES
            )
            if relative and baseline is not None:
                used_baseline = True
                spread = max(baseline.std, 0.1 * baseline.mean, 1.0)
                fraction = min(1.0, max(0.0, (raw - baseline.mean) / spread / RELATIVE_FULL_AT))
            elif rule.saturation is not None:
                fraction = _log_scaled(raw, rule.saturation)
            elif component is Component.AIR_ALERTS:
                fraction = min(1.0, raw / 5)
            else:
                fraction = min(1.0, raw)
            scores.append(
                ComponentScore(
                    component=component,
                    raw=round(raw, 3),
                    points=round(fraction * rule.max_points, 1),
                    max_points=rule.max_points,
                    rule=rule.description,
                    mode=ScoreMode.RELATIVE if relative else ScoreMode.ABSOLUTE,
                    baseline_mean=round(baseline.mean, 3) if relative and baseline else None,
                    evidence=tuple(tally.evidence or ()) if tally else (),
                )
            )
        # Zero-score countries are kept: their raw values feed the baselines.
        results.append(
            CountrySignal(
                iso2=code,
                name=names[code],
                score=round(sum(s.points for s in scores), 1),
                components=tuple(scores),
                computed_at=at,
                has_baseline=used_baseline,
            )
        )
    results.sort(key=lambda r: (r.score, r.iso2), reverse=True)
    return results


class HistoryPoint(DomainModel):
    at: datetime
    score: float
    raw: dict[Component, float] = Field(default_factory=dict)


class SignalHistoryRepository(Protocol):
    """Hourly snapshots, so the index can show its evolution."""

    async def save(self, signals: Sequence[CountrySignal], at: datetime) -> None: ...

    async def history(self, iso2: str, since: datetime) -> list[HistoryPoint]: ...

    async def samples(self, since: datetime) -> list[tuple[str, dict[Component, float]]]:
        """Raw component values of every snapshot since ``since`` (for baselines)."""
        ...

    async def prune(self, before: datetime) -> int: ...
