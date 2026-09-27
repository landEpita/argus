"""
Alert rules: management, evaluation and delivery.

Each evaluation gathers only the data the owner's enabled rules need, runs
the pure evaluators, drops what already fired (dedupe key per rule), stores
the new alerts and sends them to the rule's channels. A feed that fails skips
the rules that need it for this round; nothing is invented to fill the gap.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from argus.domain.alerts import (
    MAX_CHANNELS_PER_OWNER,
    MAX_RULES_PER_OWNER,
    AircraftParams,
    Alert,
    AlertRepository,
    Channel,
    ChannelDraft,
    ChannelKind,
    Delivery,
    Rule,
    RuleDraft,
    RuleKind,
    Severity,
    Snapshot,
    evaluate,
    parse_params,
)
from argus.domain.aviation import AircraftTrack
from argus.domain.convergence import Convergence
from argus.domain.errors import ConflictError, LimitExceededError, NotFoundError
from argus.domain.events import GeoEvent
from argus.domain.markets import Quote
from argus.domain.news import Story
from argus.domain.signal_index import CountrySignal
from argus.infra.clock import WallClock
from argus.providers.errors import AllProvidersFailedError, NoProviderError, ProviderError

logger = logging.getLogger(__name__)

MAX_NEW_PER_RULE = 10  # a new keyword rule must not flood the channels with the backlog
WINDOW_HOURS = 2


class Feeds(Protocol):
    """What the rules read. Each may raise NoProviderError / AllProvidersFailedError."""

    async def earthquakes(self, hours: float) -> list[GeoEvent]: ...
    async def disasters(self, hours: float) -> list[GeoEvent]: ...
    async def stories(self, hours: float) -> list[Story]: ...
    async def quotes(self) -> list[Quote]: ...
    async def signals(self) -> list[CountrySignal]: ...
    async def convergences(self) -> list[Convergence]: ...
    async def track(self, icao24: str) -> AircraftTrack | None: ...
    async def digest(self, owner: str) -> tuple[str, list[str]]: ...


class Sender(Protocol):
    def supports(self, kind: ChannelKind) -> bool: ...
    async def send(self, channel: Channel, alert: Alert) -> None: ...


@dataclass(frozen=True, slots=True)
class Evaluation:
    fired: list[Alert]
    skipped: list[str]  # inputs that failed this round


_UNAVAILABLE = (NoProviderError, AllProvidersFailedError)


class AlertsService:
    def __init__(
        self, repo: AlertRepository, feeds: Feeds, sender: Sender, clock: WallClock
    ) -> None:
        self._repo = repo
        self._feeds = feeds
        self._sender = sender
        self._clock = clock
        self._lock = asyncio.Lock()

    # ── Rules ──────────────────────────────────────────────────────────────

    async def rules(self, owner: str) -> list[Rule]:
        return await self._repo.rules(owner)

    async def create_rule(self, owner: str, draft: RuleDraft) -> Rule:
        existing = await self._repo.rules(owner)
        if len(existing) >= MAX_RULES_PER_OWNER:
            raise LimitExceededError(f"at most {MAX_RULES_PER_OWNER} rules")
        await self._check_channels(owner, draft.channels)
        rule = Rule(**draft.model_dump(), id=uuid.uuid4().hex, created_at=self._clock.utcnow())
        return await self._repo.save_rule(owner, rule)

    async def update_rule(self, owner: str, rule_id: str, draft: RuleDraft) -> Rule:
        current = await self._rule(owner, rule_id)
        await self._check_channels(owner, draft.channels)
        rule = current.model_copy(update=draft.model_dump())
        return await self._repo.save_rule(owner, Rule.model_validate(rule.model_dump()))

    async def delete_rule(self, owner: str, rule_id: str) -> None:
        if not await self._repo.delete_rule(owner, rule_id):
            raise NotFoundError("rule", rule_id)

    async def _rule(self, owner: str, rule_id: str) -> Rule:
        found = next((r for r in await self._repo.rules(owner) if r.id == rule_id), None)
        if found is None:
            raise NotFoundError("rule", rule_id)
        return found

    async def _check_channels(self, owner: str, ids: Sequence[str]) -> None:
        known = {c.id for c in await self._repo.channels(owner)}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise NotFoundError("channel", unknown[0])

    # ── Channels ───────────────────────────────────────────────────────────

    async def channels(self, owner: str) -> list[Channel]:
        return await self._repo.channels(owner)

    def supports(self, kind: ChannelKind) -> bool:
        return self._sender.supports(kind)

    async def create_channel(self, owner: str, draft: ChannelDraft) -> Channel:
        existing = await self._repo.channels(owner)
        if len(existing) >= MAX_CHANNELS_PER_OWNER:
            raise LimitExceededError(f"at most {MAX_CHANNELS_PER_OWNER} channels")
        if not self._sender.supports(draft.kind):
            raise ConflictError(f"{draft.kind.value} is not configured on the server")
        channel = Channel(
            **draft.model_dump(), id=uuid.uuid4().hex, created_at=self._clock.utcnow()
        )
        return await self._repo.save_channel(owner, channel)

    async def delete_channel(self, owner: str, channel_id: str) -> None:
        if not await self._repo.delete_channel(owner, channel_id):
            raise NotFoundError("channel", channel_id)
        for rule in await self._repo.rules(owner):  # rules stop pointing at it
            if channel_id in rule.channels:
                kept = tuple(c for c in rule.channels if c != channel_id)
                await self._repo.save_rule(owner, rule.model_copy(update={"channels": kept}))

    async def test_channel(self, owner: str, channel_id: str) -> Delivery:
        channel = next((c for c in await self._repo.channels(owner) if c.id == channel_id), None)
        if channel is None:
            raise NotFoundError("channel", channel_id)
        probe = Alert(
            id="test", key="test", rule_id="test", rule_name="Test", at=self._clock.utcnow(),
            title="Argus test alert", detail="If you read this, the channel works.",
            source="Argus", severity=Severity.INFO,
        )  # fmt: skip
        return await self._deliver(channel, probe)

    # ── Feed ───────────────────────────────────────────────────────────────

    async def alerts(self, owner: str, limit: int = 50, unread_only: bool = False) -> list[Alert]:
        return await self._repo.alerts(owner, limit, unread_only)

    async def unread(self, owner: str) -> int:
        return await self._repo.unread(owner)

    async def mark_read(self, owner: str, ids: Sequence[str] | None) -> int:
        return await self._repo.mark_read(owner, ids)

    # ── Evaluation ─────────────────────────────────────────────────────────

    async def evaluate(self, owner: str) -> Evaluation:
        async with self._lock:  # the loop and a manual "check now" never overlap
            rules = [r for r in await self._repo.rules(owner) if r.enabled]
            snapshot, skipped = await self._snapshot(owner, rules)
            channels = {c.id: c for c in await self._repo.channels(owner)}
            fired: list[Alert] = []
            for rule in rules:
                if _needs(rule.kind) in skipped:
                    continue
                new = 0
                for candidate in evaluate(rule, snapshot):
                    if new >= MAX_NEW_PER_RULE:
                        break
                    if await self._repo.seen(owner, rule.id, candidate.key):
                        continue
                    alert = Alert(
                        **candidate.model_dump(), id=uuid.uuid4().hex, rule_id=rule.id,
                        rule_name=rule.name, at=snapshot.now,
                    )  # fmt: skip
                    deliveries = [
                        await self._deliver(channels[cid], alert)
                        for cid in rule.channels
                        if cid in channels
                    ]
                    alert = alert.model_copy(update={"deliveries": tuple(deliveries)})
                    await self._repo.add_alert(owner, alert)
                    fired.append(alert)
                    new += 1
                if new:
                    await self._repo.save_rule(
                        owner, rule.model_copy(update={"last_fired_at": snapshot.now})
                    )
            return Evaluation(fired, sorted(skipped))

    async def _deliver(self, channel: Channel, alert: Alert) -> Delivery:
        try:
            await self._sender.send(channel, alert)
        except ProviderError as exc:
            logger.warning(
                "alert delivery failed", extra={"channel": channel.kind.value, "error": str(exc)}
            )
            return Delivery(
                channel_id=channel.id, channel_name=channel.name, ok=False, error=str(exc)
            )
        return Delivery(channel_id=channel.id, channel_name=channel.name, ok=True)

    async def _snapshot(self, owner: str, rules: Sequence[Rule]) -> tuple[Snapshot, set[str]]:
        now = self._clock.utcnow()
        kinds = {r.kind for r in rules}
        skipped: set[str] = set()

        async def attempt[T](name: str, wanted: bool, load: Callable[[], Awaitable[T]]) -> T | None:
            if not wanted:
                return None
            try:
                return await load()
            except _UNAVAILABLE:
                skipped.add(name)
                return None

        f = self._feeds
        digest_due = any(
            r.kind is RuleKind.DAILY_DIGEST and now.hour >= int(r.params.get("hour_utc", 7))
            for r in rules
        )
        # Started together, awaited one by one: concurrent and still typed.
        quakes = asyncio.create_task(
            attempt(
                "earthquakes", RuleKind.EARTHQUAKE in kinds, lambda: f.earthquakes(WINDOW_HOURS)
            )
        )
        disasters = asyncio.create_task(
            attempt("disasters", RuleKind.DISASTER_ALERT in kinds, lambda: f.disasters(24))
        )
        stories = asyncio.create_task(
            attempt("stories", RuleKind.KEYWORD in kinds, lambda: f.stories(WINDOW_HOURS))
        )
        quotes = asyncio.create_task(attempt("quotes", RuleKind.TICKER_MOVE in kinds, f.quotes))
        signals = asyncio.create_task(
            attempt("signals", RuleKind.COUNTRY_SCORE in kinds, f.signals)
        )
        cells = asyncio.create_task(
            attempt("convergences", RuleKind.CONVERGENCE in kinds, f.convergences)
        )
        digest = asyncio.create_task(attempt("digest", digest_due, lambda: f.digest(owner)))

        wanted: set[str] = set()
        for r in rules:
            params = parse_params(r.kind, r.params)
            if isinstance(params, AircraftParams):
                wanted.update(params.icao24)
        tracks: dict[str, AircraftTrack | None] = {}
        for icao24 in sorted(wanted)[:20]:
            try:
                tracks[icao24] = await f.track(icao24)
            except (ProviderError, *_UNAVAILABLE):  # not flying today (404), or no source
                tracks[icao24] = None

        snapshot = Snapshot(
            now=now,
            earthquakes=await quakes,
            disasters=await disasters,
            stories=await stories,
            quotes=await quotes,
            signals=await signals,
            convergences=await cells,
            tracks=tracks,
            digest=await digest,
        )
        return snapshot, skipped


_NEEDS = {
    RuleKind.EARTHQUAKE: "earthquakes",
    RuleKind.DISASTER_ALERT: "disasters",
    RuleKind.KEYWORD: "stories",
    RuleKind.TICKER_MOVE: "quotes",
    RuleKind.COUNTRY_SCORE: "signals",
    RuleKind.CONVERGENCE: "convergences",
    RuleKind.DAILY_DIGEST: "digest",
    RuleKind.WATCHED_AIRCRAFT: "tracks",
}


def _needs(kind: RuleKind) -> str:
    return _NEEDS[kind]


class AlertLoop:
    """Evaluates every owner's rules on a fixed cadence."""

    name = "alert-loop"

    def __init__(
        self,
        alerts: AlertsService,
        repo: AlertRepository,
        interval_s: float,
        first_delay_s: float = 30,
    ) -> None:
        self._alerts = alerts
        self._repo = repo
        self._interval_s = interval_s
        self._first_delay_s = first_delay_s
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=self.name)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> int:
        fired = 0
        for owner in await self._repo.owners():
            result = await self._alerts.evaluate(owner)
            fired += len(result.fired)
        return fired

    async def _run(self) -> None:
        await asyncio.sleep(self._first_delay_s)
        while True:
            try:
                fired = await self.run_once()
                if fired:
                    logger.info("alerts fired", extra={"count": fired})
            except asyncio.CancelledError:
                raise
            except Exception:  # one bad round must not stop the loop
                logger.exception("alert evaluation failed")
            await asyncio.sleep(self._interval_s)
