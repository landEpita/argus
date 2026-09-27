from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from argus.domain.convergence import CELL_DEG, SignalKind, SignalPoint, find
from argus.domain.events import EventCategory, GeoEvent
from argus.domain.geo import GeoPoint
from argus.domain.news import NewsCategory, Ownership, Story, StorySource
from argus.domain.signal_index import (
    MIN_BASELINE_SAMPLES,
    RULES,
    SINGLE_SOURCE_WEIGHT,
    Baseline,
    Component,
    CountrySignal,
    ScoreMode,
    baselines_from,
    compute,
)

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
NAMES = {"UA": "Ukraine", "IR": "Iran", "JP": "Japan", "PK": "Pakistan"}


def event(
    i: str,
    country: str | None,
    category: EventCategory = EventCategory.ARMED_CONFLICT,
    **extra: Any,
) -> GeoEvent:
    # Two sources by default: full weight, unless a test says otherwise.
    details: dict[str, Any] = {"num_sources": 2}
    if country:
        details["country_iso2"] = country
    details |= extra.pop("details", {})
    return GeoEvent(
        id=i,
        category=category,
        title=i,
        position=GeoPoint(lat=1, lon=1),
        occurred_at=NOW,
        source="t",
        details=details,
        **extra,
    )


def story(i: str, countries: tuple[str, ...], outlets: int) -> Story:
    return Story(
        id=i,
        title=i,
        url="u",
        articles=(),
        countries=countries,
        category=NewsCategory.WORLD,
        state_media_only=False,
        sources=tuple(
            StorySource(id=f"s{n}", name=f"S{n}", tier=1, ownership=Ownership.PRIVATE)
            for n in range(outlets)
        ),
        first_seen=NOW,
        last_updated=NOW,
    )


def _empty() -> dict[str, Any]:
    return dict(violence=[], air_alerts=[], outages=[], disasters=[], earthquakes=[], stories=[])


def compute_with(baselines: Any, **inputs: Any) -> list[Any]:
    return compute(**(_empty() | inputs), names=NAMES, at=NOW, baselines=baselines)


def run(**inputs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        violence=[], air_alerts=[], outages=[], disasters=[], earthquakes=[], stories=[]
    )
    results = compute(**(defaults | inputs), names=NAMES, at=NOW)
    return {r.iso2: r for r in results}


class TestIndex:
    def test_points_add_up_to_100_at_saturation(self) -> None:
        assert sum(r.max_points for r in RULES.values()) == 100
        results = run(
            violence=[event(f"v{i}", "UA", severity=1.0) for i in range(60)],
            air_alerts=[event(f"a{i}", "UA", EventCategory.AIR_RAID_ALERT) for i in range(6)],
            outages=[
                event(
                    "o",
                    "UA",
                    EventCategory.INTERNET_OUTAGE,
                    severity=1.0,
                    details={"ongoing": True},
                )
            ],
            disasters=[event("d", "UA", EventCategory.FLOOD, severity=1.0)],
            stories=[story(f"s{i}", ("UA",), 5) for i in range(30)],
        )
        assert results["UA"].score == 100

    def test_every_component_is_explained(self) -> None:
        ua = run(violence=[event("v1", "UA", severity=0.8)])["UA"]
        by = {c.component: c for c in ua.components}
        assert set(by) == set(Component)
        violence = by[Component.REPORTED_VIOLENCE]
        assert violence.raw == pytest.approx(0.25 + 0.75 * 0.8)
        assert violence.evidence == ("v1",)
        assert violence.rule.startswith("violent events")
        assert by[Component.AIR_ALERTS].points == 0

    def test_log_scaling_saturates(self) -> None:
        few = run(violence=[event(f"v{i}", "UA", severity=1.0) for i in range(5)])["UA"].score
        many = run(violence=[event(f"v{i}", "UA", severity=1.0) for i in range(500)])["UA"].score
        assert 0 < few < many <= 35

    def test_ended_outages_and_minor_quakes_do_not_count(self) -> None:
        results = run(
            outages=[
                event(
                    "o",
                    "IR",
                    EventCategory.INTERNET_OUTAGE,
                    severity=1.0,
                    details={"ongoing": False},
                )
            ],
            earthquakes=[event("q", "JP", EventCategory.EARTHQUAKE, magnitude=4.2)],
        )
        assert all(r.score == 0 for r in results.values())

    def test_strong_quake_counts_as_hazard(self) -> None:
        jp = run(earthquakes=[event("q", "JP", EventCategory.EARTHQUAKE, magnitude=6.5)])["JP"]
        hazard = next(c for c in jp.components if c.component is Component.NATURAL_HAZARDS)
        assert hazard.points == pytest.approx(7.5)  # (6.5-5)/3 of 15

    def test_news_attention_weights_outlets(self) -> None:
        one = run(stories=[story("s", ("PK",), 1)])["PK"].score
        five = run(stories=[story("s", ("PK",), 5)])["PK"].score
        assert five > one

    def test_events_without_country_or_unknown_countries_are_ignored(self) -> None:
        assert run(violence=[event("v", None), event("w", "ZZ")]) == {}

    def test_single_source_events_weigh_less(self) -> None:
        solid = run(violence=[event("v", "UA", severity=0.0, details={"num_sources": 4})])["UA"]
        thin = run(violence=[event("v", "UA", severity=0.0, details={"num_sources": 1})])["UA"]

        def raw(signal: CountrySignal) -> float:
            return next(
                c.raw for c in signal.components if c.component is Component.REPORTED_VIOLENCE
            )

        assert raw(solid) == pytest.approx(0.25)
        assert raw(thin) == pytest.approx(0.25 * SINGLE_SOURCE_WEIGHT)

    def test_relative_mode_needs_enough_samples(self) -> None:
        few = {
            "UA": {
                Component.REPORTED_VIOLENCE: Baseline(
                    mean=1, std=0.5, samples=MIN_BASELINE_SAMPLES - 1
                )
            }
        }
        [ua] = compute_with(few, violence=[event("v", "UA", severity=1.0)])
        assert ua.has_baseline is False
        assert ua.components[0].mode is ScoreMode.ABSOLUTE

    def test_relative_points_scale_with_deviation(self) -> None:
        base = {"UA": {Component.REPORTED_VIOLENCE: Baseline(mean=10, std=2, samples=100)}}

        def score(n: int) -> float:
            [ua] = compute_with(
                base, violence=[event(f"v{i}", "UA", severity=1.0) for i in range(n)]
            )
            return float(ua.score)

        assert score(10) == 0  # at the usual level
        assert 0 < score(14) < score(16) == 35  # +2 std partial, +3 std full

    def test_hazards_stay_absolute_even_with_a_baseline(self) -> None:
        base = {"JP": {Component.NATURAL_HAZARDS: Baseline(mean=1, std=0, samples=500)}}
        [jp] = compute_with(
            base, earthquakes=[event("q", "JP", EventCategory.EARTHQUAKE, magnitude=8.0)]
        )
        assert jp.score == 15
        assert jp.has_baseline is False

    def test_baselines_from_samples(self) -> None:
        b = baselines_from(
            [("UA", {Component.AIR_ALERTS: 2.0}), ("UA", {Component.AIR_ALERTS: 4.0})]
        )
        assert b["UA"][Component.AIR_ALERTS] == Baseline(mean=3.0, std=1.0, samples=2)

    def test_sorted_by_score(self) -> None:
        results = compute(
            violence=[event("v", "UA", severity=1.0)],
            air_alerts=[],
            outages=[],
            disasters=[],
            earthquakes=[],
            stories=[story("s", ("IR",), 1)],
            names=NAMES,
            at=NOW,
        )
        assert [r.iso2 for r in results] == ["UA", "IR"]


def point(
    kind: SignalKind, lat: float, lon: float, i: str = "x", country: str | None = None
) -> SignalPoint:
    return SignalPoint(
        kind=kind,
        id=f"{kind}:{i}",
        label=i,
        position=GeoPoint(lat=lat, lon=lon),
        at=NOW - timedelta(minutes=int(lat)),
        country=country,
    )


class TestConvergence:
    def test_needs_two_distinct_kinds_in_a_cell(self) -> None:
        points = [
            point(SignalKind.REPORTED_VIOLENCE, 48.5, 35.1, "a", "UA"),
            point(SignalKind.REPORTED_VIOLENCE, 48.6, 35.2, "b", "UA"),
            point(SignalKind.AIR_ALERT, 48.4, 35.0, "c", "UA"),
            point(SignalKind.REPORTED_VIOLENCE, 10.0, 10.0, "lonely"),
        ]
        [c] = find(points)
        assert {k.kind for k in c.kinds} == {SignalKind.REPORTED_VIOLENCE, SignalKind.AIR_ALERT}
        assert c.kinds[0].count == 2
        assert c.country == "UA"
        assert c.cell.east - c.cell.west == CELL_DEG
        assert c.cell.contains(c.center)

    def test_diversity_ranks_above_volume(self) -> None:
        busy = [point(SignalKind.REPORTED_VIOLENCE, 30.5, 30.5, str(i)) for i in range(50)] + [
            point(SignalKind.FIRE, 30.5, 30.5)
        ]
        diverse = [
            point(k, 10.5, 10.5)
            for k in (SignalKind.REPORTED_VIOLENCE, SignalKind.FIRE, SignalKind.MILITARY_AIRCRAFT)
        ]
        ranked = find(busy + diverse)
        assert [len(c.kinds) for c in ranked] == [3, 2]

    def test_country_is_none_when_no_signal_says(self) -> None:
        [c] = find([point(SignalKind.MILITARY_AIRCRAFT, 1, 1), point(SignalKind.FIRE, 1, 1)])
        assert c.country is None

    def test_examples_are_unique_and_capped(self) -> None:
        points = (
            [point(SignalKind.FIRE, 1, 1, "same") for _ in range(5)]
            + [point(SignalKind.FIRE, 1, 1, str(i)) for i in range(5)]
            + [point(SignalKind.AIR_ALERT, 1, 1)]
        )
        [c] = find(points)
        fire = next(k for k in c.kinds if k.kind is SignalKind.FIRE)
        assert fire.examples == ("same", "0", "1")

    def test_negative_coordinates_bin_correctly(self) -> None:
        [c] = find([point(SignalKind.FIRE, -0.5, -0.5), point(SignalKind.AIR_ALERT, -1.5, -1.5)])
        assert (c.cell.west, c.cell.south) == (-2, -2)
