"""The alerts service over the real repository (SQLite, and Postgres in CI)."""

from datetime import UTC, datetime

import pytest

from argus.domain.alerts import Alert, Channel, ChannelDraft, ChannelKind, RuleDraft, RuleKind
from argus.domain.aviation import AircraftTrack
from argus.domain.convergence import Convergence
from argus.domain.errors import ConflictError, LimitExceededError, NotFoundError
from argus.domain.events import EventCategory, GeoEvent
from argus.domain.geo import GeoPoint
from argus.domain.markets import Quote
from argus.domain.news import Story
from argus.domain.signal_index import CountrySignal
from argus.infra.db import Database
from argus.infra.db.repositories import SqlAlertRepository
from argus.providers.errors import AllProvidersFailedError, ProviderUnavailableError
from argus.services.alerts import AlertLoop, AlertsService
from tests.fakes import FakeWallClock

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
WEBHOOK = ChannelDraft(
    name="hook", kind=ChannelKind.WEBHOOK, config={"url": "https://hooks.example/argus"}
)


def quake(i: str, magnitude: float) -> GeoEvent:
    return GeoEvent(
        id=i, category=EventCategory.EARTHQUAKE, title=f"quake {i}",
        position=GeoPoint(lat=23, lon=121), occurred_at=NOW, source="usgs", magnitude=magnitude,
    )  # fmt: skip


class Feeds:
    def __init__(self) -> None:
        self.quakes = [quake("a", 6.4), quake("b", 4.0)]
        self.fail_quakes = False
        self.calls: list[str] = []

    async def earthquakes(self, hours: float) -> list[GeoEvent]:
        self.calls.append("earthquakes")
        if self.fail_quakes:
            raise AllProvidersFailedError("events.earthquakes", [])
        return self.quakes

    async def disasters(self, hours: float) -> list[GeoEvent]:
        return []

    async def stories(self, hours: float) -> list[Story]:
        self.calls.append("stories")
        return []

    async def quotes(self) -> list[Quote]:
        return []

    async def signals(self) -> list[CountrySignal]:
        return []

    async def convergences(self) -> list[Convergence]:
        return []

    async def track(self, icao24: str) -> AircraftTrack | None:
        return None

    async def digest(self, owner: str) -> tuple[str, list[str]]:
        self.calls.append("digest")
        return "Brent -8.59 %.", ["Brent -8.59 %"]


class Sender:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def supports(self, kind: ChannelKind) -> bool:
        return kind is not ChannelKind.EMAIL

    async def send(self, channel: Channel, alert: Alert) -> None:
        if self.fail:
            raise ProviderUnavailableError("webhook", "HTTP 503")
        self.sent.append((channel.name, alert.title))


Env = tuple[AlertsService, "Feeds", "Sender", SqlAlertRepository]


@pytest.fixture
def service(database: Database) -> Env:
    feeds, sender, repo = Feeds(), Sender(), SqlAlertRepository(database)
    return AlertsService(repo, feeds, sender, FakeWallClock(NOW)), feeds, sender, repo


async def test_a_fact_fires_once_and_reaches_its_channels(service: Env) -> None:
    alerts, feeds, sender, _ = service
    hook = await alerts.create_channel("alice", WEBHOOK)
    rule = await alerts.create_rule(
        "alice",
        RuleDraft(
            name="Big quakes",
            kind=RuleKind.EARTHQUAKE,
            params={"min_magnitude": 6},
            channels=(hook.id,),
        ),
    )
    first = await alerts.evaluate("alice")
    assert [a.title for a in first.fired] == ["M 6.4 · quake a"]
    assert first.fired[0].deliveries[0].ok is True
    assert sender.sent == [("hook", "M 6.4 · quake a")]
    assert feeds.calls == ["earthquakes"]  # only what the rules need is read
    assert (await alerts.evaluate("alice")).fired == []  # deduplicated
    assert await alerts.unread("alice") == 1
    [stored] = await alerts.alerts("alice")
    assert (stored.rule_name, stored.layer, stored.read) == ("Big quakes", "earthquakes", False)
    [saved] = await alerts.rules("alice")
    assert saved.id == rule.id
    assert saved.last_fired_at == NOW
    assert await alerts.mark_read("alice", None) == 1
    assert await alerts.unread("alice") == 0
    assert await alerts.alerts("bob") == []  # scoped by owner


async def test_failed_deliveries_are_recorded_and_failed_inputs_skipped(database: Database) -> None:
    feeds, repo = Feeds(), SqlAlertRepository(database)
    alerts = AlertsService(repo, feeds, Sender(fail=True), FakeWallClock(NOW))
    hook = await alerts.create_channel("alice", WEBHOOK)
    await alerts.create_rule(
        "alice",
        RuleDraft(
            name="q", kind=RuleKind.EARTHQUAKE, params={"min_magnitude": 6}, channels=(hook.id,)
        ),
    )
    feeds.fail_quakes = True
    assert (await alerts.evaluate("alice")).skipped == ["earthquakes"]
    feeds.fail_quakes = False
    [fired] = (await alerts.evaluate("alice")).fired
    assert fired.deliveries[0].ok is False
    assert fired.deliveries[0].error == "[webhook] HTTP 503"
    assert (await alerts.test_channel("alice", hook.id)).ok is False


async def test_rules_and_channels_are_checked(service: Env) -> None:
    alerts, _, _, _ = service
    with pytest.raises(NotFoundError):
        await alerts.create_rule(
            "alice", RuleDraft(name="x", kind=RuleKind.EARTHQUAKE, channels=("nope",))
        )
    with pytest.raises(ConflictError):  # e-mail without SMTP on the server
        await alerts.create_channel(
            "alice", ChannelDraft(name="mail", kind=ChannelKind.EMAIL, config={"to": "a@b.io"})
        )
    hook = await alerts.create_channel("alice", WEBHOOK)
    rule = await alerts.create_rule(
        "alice", RuleDraft(name="x", kind=RuleKind.EARTHQUAKE, channels=(hook.id,))
    )
    await alerts.delete_channel("alice", hook.id)
    [kept] = await alerts.rules("alice")
    assert kept.id == rule.id
    assert kept.channels == ()  # no dangling channel
    updated = await alerts.update_rule(
        "alice", rule.id, RuleDraft(name="renamed", kind=RuleKind.EARTHQUAKE, enabled=False)
    )
    assert (updated.name, updated.enabled) == ("renamed", False)
    await alerts.delete_rule("alice", rule.id)
    with pytest.raises(NotFoundError):
        await alerts.delete_rule("alice", rule.id)
    with pytest.raises(NotFoundError):
        await alerts.test_channel("alice", "nope")


async def test_limits(service: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    alerts, _, _, _ = service
    monkeypatch.setattr("argus.services.alerts.MAX_RULES_PER_OWNER", 1)
    await alerts.create_rule("alice", RuleDraft(name="1", kind=RuleKind.EARTHQUAKE))
    with pytest.raises(LimitExceededError):
        await alerts.create_rule("alice", RuleDraft(name="2", kind=RuleKind.EARTHQUAKE))


async def test_new_rules_do_not_flood(service: Env) -> None:
    alerts, feeds, _, _ = service
    feeds.quakes = [quake(str(i), 6.5) for i in range(30)]
    await alerts.create_rule("alice", RuleDraft(name="q", kind=RuleKind.EARTHQUAKE))
    assert len((await alerts.evaluate("alice")).fired) == 10
    assert len((await alerts.evaluate("alice")).fired) == 10  # the rest, next rounds


async def test_the_digest_and_the_loop(service: Env) -> None:
    alerts, _, _, repo = service
    await alerts.create_rule(
        "alice", RuleDraft(name="Morning", kind=RuleKind.DAILY_DIGEST, params={"hour_utc": 7})
    )
    await alerts.create_rule("bob", RuleDraft(name="Off", kind=RuleKind.EARTHQUAKE, enabled=False))
    loop = AlertLoop(alerts, repo, interval_s=3600)
    assert await loop.run_once() == 1  # alice's digest; bob has no enabled rule
    [digest] = await alerts.alerts("alice")
    assert (digest.title, digest.detail) == ("Daily digest", "Brent -8.59 %.")
    await loop.start()
    await loop.stop()
