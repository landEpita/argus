from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from argus.domain.alerts import (
    Channel,
    ChannelDraft,
    ChannelKind,
    Rule,
    RuleDraft,
    RuleKind,
    Severity,
    Snapshot,
    evaluate,
)
from argus.domain.aviation import AircraftTrack, TrackPoint
from argus.domain.convergence import Convergence, KindCount, SignalKind
from argus.domain.events import EventCategory, GeoEvent
from argus.domain.geo import BoundingBox, GeoPoint
from argus.domain.markets import WATCH_SET, Quote
from argus.domain.signal_index import CountrySignal
from tests.unit.domain.test_signals import story

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


def rule(kind: RuleKind, **params: object) -> Rule:
    draft = RuleDraft(name=kind.value, kind=kind, params=dict(params))
    return Rule(**draft.model_dump(), id="r1", created_at=NOW)


def event(i: str, category: EventCategory, **extra: object) -> GeoEvent:
    details = extra.pop("details", {})
    title = str(extra.pop("title", i))
    return GeoEvent(
        id=i, category=category, title=title, position=GeoPoint(lat=23.3, lon=121.9),
        occurred_at=NOW, source="t", details=details, **extra,
    )  # fmt: skip


def test_params_are_validated_and_normalised() -> None:
    r = rule(RuleKind.WATCHED_AIRCRAFT, icao24=["3C6444"])
    assert r.params == {"icao24": ["3c6444"]}
    assert rule(RuleKind.EARTHQUAKE, countries=["tw"]).params["countries"] == ["TW"]
    assert rule(RuleKind.KEYWORD, keywords=["  Strait  of Hormuz "]).params["keywords"] == [
        "strait of hormuz"
    ]
    for kind, bad in [
        (RuleKind.WATCHED_AIRCRAFT, {"icao24": ["xyz"]}),
        (RuleKind.EARTHQUAKE, {"min_magnitude": 1}),
        (RuleKind.DISASTER_ALERT, {"min_level": "green"}),
        (RuleKind.COUNTRY_SCORE, {"countries": ["France"]}),
        (RuleKind.KEYWORD, {"keywords": []}),
        (RuleKind.DAILY_DIGEST, {"hour_utc": 24}),
    ]:
        with pytest.raises(ValidationError):
            RuleDraft(name="x", kind=kind, params=bad)


def test_channel_configs_are_validated_and_secrets_stay_out_of_hints() -> None:
    discord = ChannelDraft(
        name="ops",
        kind=ChannelKind.DISCORD,
        config={"url": "https://discord.com/api/webhooks/1/secret"},
    )
    assert Channel(**discord.model_dump(), id="c", created_at=NOW).hint() == "discord.com"
    bot = ChannelDraft(
        name="tg", kind=ChannelKind.TELEGRAM,
        config={"bot_token": "123456:" + "A" * 30, "chat_id": "-100123"},
    )  # fmt: skip
    assert Channel(**bot.model_dump(), id="c", created_at=NOW).hint() == "chat -100123"
    for kind, bad in [
        (ChannelKind.WEBHOOK, {"url": "ftp://x"}),
        (ChannelKind.DISCORD, {"url": "https://evil.example/api/webhooks/1"}),
        (ChannelKind.TELEGRAM, {"bot_token": "nope", "chat_id": "1"}),
        (ChannelKind.EMAIL, {"to": "not-an-address"}),
    ]:
        with pytest.raises(ValidationError):
            ChannelDraft(name="x", kind=kind, config=bad)


def test_earthquakes_by_magnitude_and_country() -> None:
    quakes = [
        event("big", EventCategory.EARTHQUAKE, magnitude=7.1, details={"country_iso2": "TW"}),
        event("small", EventCategory.EARTHQUAKE, magnitude=5.0, details={"country_iso2": "TW"}),
        event("far", EventCategory.EARTHQUAKE, magnitude=6.5, details={"country_iso2": "JP"}),
    ]
    snap = Snapshot(now=NOW, earthquakes=quakes)
    [c] = evaluate(rule(RuleKind.EARTHQUAKE, min_magnitude=6, countries=["TW"]), snap)
    assert (c.key, c.severity, c.layer) == ("eq:big", Severity.CRITICAL, "earthquakes")
    assert len(evaluate(rule(RuleKind.EARTHQUAKE, min_magnitude=6), snap)) == 2
    usgs = event("u", EventCategory.EARTHQUAKE, magnitude=6.1, title="M 6.1 - 48 km SSE of Hualien")
    [titled] = evaluate(rule(RuleKind.EARTHQUAKE), Snapshot(now=NOW, earthquakes=[usgs]))
    assert titled.title == "M 6.1 - 48 km SSE of Hualien"  # the magnitude is not repeated


def test_disasters_by_level() -> None:
    snap = Snapshot(
        now=NOW,
        disasters=[
            event("a", EventCategory.TROPICAL_CYCLONE, details={"alert_level": "orange"}),
            event("b", EventCategory.FLOOD, details={"alert_level": "red"}),
            event("c", EventCategory.FLOOD, details={"alert_level": "green"}),
        ],
    )
    assert [c.key for c in evaluate(rule(RuleKind.DISASTER_ALERT, min_level="red"), snap)] == [
        "gdacs:b:red"
    ]
    assert len(evaluate(rule(RuleKind.DISASTER_ALERT, min_level="orange"), snap)) == 2


def test_keywords_in_headlines_with_enough_outlets() -> None:
    s1 = story("1", ("IR",), 3).model_copy(update={"title": "Tankers slow in the Strait of Hormuz"})
    s2 = story("2", ("IR",), 1).model_copy(
        update={"title": "Hormuz talks", "state_media_only": True}
    )
    snap = Snapshot(now=NOW, stories=[s1, s2])
    hits = evaluate(rule(RuleKind.KEYWORD, keywords=["hormuz"]), snap)
    assert [c.key for c in hits] == ["kw:hormuz:1", "kw:hormuz:2"]
    assert hits[1].unverified is True
    assert len(evaluate(rule(RuleKind.KEYWORD, keywords=["hormuz"], min_outlets=2), snap)) == 1


def test_ticker_moves_once_a_day_per_direction() -> None:
    brent = next(i for i in WATCH_SET if i.symbol == "BZ=F")
    gold = next(i for i in WATCH_SET if i.symbol == "GC=F")
    quotes = [
        Quote(instrument=brent, price=97.44, change_pct=-8.59, as_of=NOW, source="yahoo"),
        Quote(instrument=gold, price=4321, change_pct=0.5, as_of=NOW, source="yahoo"),
    ]
    [c] = evaluate(rule(RuleKind.TICKER_MOVE, min_change_pct=3), Snapshot(now=NOW, quotes=quotes))
    assert c.key == "tk:BZ=F:2026-09-27:down"
    assert c.title == "Brent crude -8.59 %"
    assert (
        evaluate(rule(RuleKind.TICKER_MOVE, symbols=["GC=F"]), Snapshot(now=NOW, quotes=quotes))
        == []
    )


def test_country_scores_and_convergences() -> None:
    signal = CountrySignal(
        iso2="UA", name="Ukraine", score=72, has_baseline=False, computed_at=NOW, components=()
    )
    [c] = evaluate(rule(RuleKind.COUNTRY_SCORE, min_score=60), Snapshot(now=NOW, signals=[signal]))
    assert "not a stability measure" in c.detail
    cell = Convergence(
        id="cell:1", cell=BoundingBox(west=32, south=48, east=34, north=50),
        center=GeoPoint(lat=49, lon=33),
        kinds=(KindCount(kind=SignalKind.REPORTED_VIOLENCE, count=3, examples=()),
               KindCount(kind=SignalKind.AIR_ALERT, count=2, examples=())),
        score=4.5, latest=NOW, country="UA",
    )  # fmt: skip
    snap = Snapshot(now=NOW, convergences=[cell])
    # Only one verified kind: press-coded violence does not count.
    assert evaluate(rule(RuleKind.CONVERGENCE, min_verified_kinds=2), snap) == []
    assert len(evaluate(rule(RuleKind.CONVERGENCE, min_verified_kinds=1), snap)) == 1


def test_a_watched_aircraft_must_have_been_seen_recently() -> None:
    def track(minutes_ago: int) -> AircraftTrack:
        point = TrackPoint(
            at=NOW - timedelta(minutes=minutes_ago),
            position=GeoPoint(lat=46, lon=9),
            altitude_m=10668,
        )
        return AircraftTrack(icao24="3c6444", callsign="GAF618", points=(point,), source="adsblol")

    r = rule(RuleKind.WATCHED_AIRCRAFT, icao24=["3c6444", "abcdef"])
    [c] = evaluate(r, Snapshot(now=NOW, tracks={"3c6444": track(5), "abcdef": None}))
    assert (c.title, c.key) == ("GAF618 is flying", "ac:3c6444:2026-09-27")
    assert "10668 m" in c.detail
    assert evaluate(r, Snapshot(now=NOW, tracks={"3c6444": track(40)})) == []


def test_the_digest_fires_once_after_its_hour() -> None:
    r = rule(RuleKind.DAILY_DIGEST, hour_utc=7)
    [c] = evaluate(r, Snapshot(now=NOW, digest=("Brent -8.59 %.", ["Brent -8.59 %"])))
    assert (c.key, c.detail) == ("digest:2026-09-27", "Brent -8.59 %.")
    early = NOW.replace(hour=6)
    assert evaluate(r, Snapshot(now=early, digest=("x", []))) == []
    assert evaluate(r, Snapshot(now=NOW)) == []


def test_weekly_digest_is_keyed_by_iso_week() -> None:
    from argus.domain.alerts import DigestParams, digest_key

    monday = datetime(2026, 9, 28, 8, tzinfo=UTC)
    weekly = DigestParams(frequency="weekly", weekday=0, hour_utc=7)
    assert digest_key(weekly, monday) == "digest:2026-W40"
    assert digest_key(weekly, monday.replace(hour=6)) is None
    assert digest_key(weekly, datetime(2026, 9, 29, 8, tzinfo=UTC)) is None  # Tuesday
    assert digest_key(DigestParams(), monday) == "digest:2026-09-28"
    r = rule(RuleKind.DAILY_DIGEST, frequency="weekly", weekday=0)
    [c] = evaluate(r, Snapshot(now=monday, digest=("text", [])))
    assert (c.title, c.key) == ("Weekly digest", "digest:2026-W40")


def test_quiet_hours_in_the_owner_time_zone() -> None:
    from datetime import time

    from argus.domain.alerts import AlertSettings, holds, in_quiet_hours

    night = AlertSettings(timezone="Europe/Paris", quiet_start=time(22), quiet_end=time(7))
    # 21:30 UTC is 23:30 in Paris (CEST): quiet. 06:30 UTC is 08:30: not.
    assert in_quiet_hours(night, datetime(2026, 9, 27, 21, 30, tzinfo=UTC)) is True
    assert in_quiet_hours(night, datetime(2026, 9, 28, 4, 0, tzinfo=UTC)) is True
    assert in_quiet_hours(night, datetime(2026, 9, 28, 6, 30, tzinfo=UTC)) is False
    lunch = AlertSettings(quiet_start=time(12), quiet_end=time(14))
    assert in_quiet_hours(lunch, datetime(2026, 9, 27, 13, tzinfo=UTC)) is True
    assert in_quiet_hours(lunch, datetime(2026, 9, 27, 15, tzinfo=UTC)) is False
    assert in_quiet_hours(AlertSettings(), NOW) is False
    late = datetime(2026, 9, 27, 21, 30, tzinfo=UTC)
    assert holds(night, Severity.WARNING, late) is True
    assert holds(night, Severity.CRITICAL, late) is False  # critical still goes through
    strict = night.model_copy(update={"critical_breaks_quiet": False})
    assert holds(strict, Severity.CRITICAL, late) is True
    with pytest.raises(ValidationError):
        AlertSettings(timezone="Mars/Olympus")
