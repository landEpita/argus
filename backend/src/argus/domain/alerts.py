"""
Alert rules, delivery channels and fired alerts.

Rules are evaluated against a snapshot of what the feeds say now; each rule
kind is a pure function from (params, snapshot) to candidates, and every
candidate carries a dedupe key so the same fact fires once. Nothing here does
I/O: the service gathers the snapshot and delivers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Protocol

from pydantic import AfterValidator, BaseModel, Field, field_validator

from argus.domain.aviation import AircraftTrack
from argus.domain.base import DomainModel
from argus.domain.convergence import Convergence
from argus.domain.events import GeoEvent
from argus.domain.markets import Quote
from argus.domain.news import Story
from argus.domain.signal_index import CountrySignal

MAX_RULES_PER_OWNER = 50
MAX_CHANNELS_PER_OWNER = 10
SEEN_WITHIN_S = 15 * 60  # "appears": a position in the last 15 minutes
UNVERIFIED_KINDS = frozenset({"reported_violence"})


class RuleKind(StrEnum):
    WATCHED_AIRCRAFT = "watched_aircraft"
    EARTHQUAKE = "earthquake"
    DISASTER_ALERT = "disaster_alert"
    KEYWORD = "keyword"
    TICKER_MOVE = "ticker_move"
    COUNTRY_SCORE = "country_score"
    CONVERGENCE = "convergence"
    DAILY_DIGEST = "daily_digest"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


def _countries(values: tuple[str, ...]) -> tuple[str, ...]:
    out = tuple(v.strip().upper() for v in values if v.strip())
    if any(len(v) != 2 or not v.isalpha() for v in out):
        raise ValueError("countries are ISO 3166-1 alpha-2 codes")
    return out


# Empty = anywhere.
Countries = Annotated[tuple[str, ...], AfterValidator(_countries)]


# ── Parameters, one model per kind ─────────────────────────────────────────


class AircraftParams(BaseModel):
    icao24: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("icao24")
    @classmethod
    def _hex(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        out = tuple(x.strip().lower() for x in v)
        if any(len(x) != 6 or any(c not in "0123456789abcdef" for c in x) for x in out):
            raise ValueError("ICAO 24-bit addresses are 6 hexadecimal characters")
        return out


class EarthquakeParams(BaseModel):
    min_magnitude: float = Field(default=6.0, ge=3, le=10)
    countries: Countries = ()


class DisasterParams(BaseModel):
    min_level: str = Field(default="red", pattern=r"^(orange|red)$")
    countries: Countries = ()


class KeywordParams(BaseModel):
    keywords: tuple[str, ...] = Field(min_length=1, max_length=20)
    min_outlets: int = Field(default=1, ge=1, le=10)

    @field_validator("keywords")
    @classmethod
    def _clean(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        out = tuple(" ".join(k.split()).casefold() for k in v if k.strip())
        if not out:
            raise ValueError("at least one keyword")
        return out


class TickerParams(BaseModel):
    min_change_pct: float = Field(default=3.0, gt=0, le=50)
    symbols: tuple[str, ...] = Field(default=(), description="Empty: the whole watch set")


class CountryScoreParams(BaseModel):
    min_score: float = Field(default=60, ge=1, le=100)
    countries: Countries = ()


class ConvergenceParams(BaseModel):
    min_verified_kinds: int = Field(default=2, ge=1, le=6)
    countries: Countries = ()


class DigestParams(BaseModel):
    hour_utc: int = Field(default=7, ge=0, le=23)


PARAMS: dict[RuleKind, type[BaseModel]] = {
    RuleKind.WATCHED_AIRCRAFT: AircraftParams,
    RuleKind.EARTHQUAKE: EarthquakeParams,
    RuleKind.DISASTER_ALERT: DisasterParams,
    RuleKind.KEYWORD: KeywordParams,
    RuleKind.TICKER_MOVE: TickerParams,
    RuleKind.COUNTRY_SCORE: CountryScoreParams,
    RuleKind.CONVERGENCE: ConvergenceParams,
    RuleKind.DAILY_DIGEST: DigestParams,
}


def parse_params(kind: RuleKind, raw: dict[str, Any]) -> BaseModel:
    return PARAMS[kind].model_validate(raw)


# ── Rules, channels, alerts ────────────────────────────────────────────────


class RuleDraft(DomainModel):
    name: str = Field(min_length=1, max_length=100)
    kind: RuleKind
    params: dict[str, Any] = Field(default_factory=dict)
    channels: tuple[str, ...] = Field(default=(), max_length=MAX_CHANNELS_PER_OWNER)
    enabled: bool = True

    @field_validator("params")
    @classmethod
    def _valid(cls, v: dict[str, Any], info: Any) -> dict[str, Any]:
        kind = info.data.get("kind")
        if kind is None:
            return v
        return parse_params(kind, v).model_dump(mode="json")


class Rule(RuleDraft):
    id: str
    created_at: datetime
    last_fired_at: datetime | None = None


class ChannelKind(StrEnum):
    WEBHOOK = "webhook"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    EMAIL = "email"


class WebhookConfig(BaseModel):
    url: str = Field(pattern=r"^https?://\S+$", max_length=500)


class DiscordConfig(BaseModel):
    url: str = Field(
        pattern=r"^https://(discord|discordapp)\.com/api/webhooks/\S+$", max_length=500
    )


class TelegramConfig(BaseModel):
    bot_token: str = Field(pattern=r"^\d+:[\w-]{20,}$", max_length=200)
    chat_id: str = Field(pattern=r"^-?\d+$|^@\w{5,}$", max_length=100)


class EmailConfig(BaseModel):
    to: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)


CHANNEL_CONFIG: dict[ChannelKind, type[BaseModel]] = {
    ChannelKind.WEBHOOK: WebhookConfig,
    ChannelKind.DISCORD: DiscordConfig,
    ChannelKind.TELEGRAM: TelegramConfig,
    ChannelKind.EMAIL: EmailConfig,
}


class ChannelDraft(DomainModel):
    name: str = Field(min_length=1, max_length=60)
    kind: ChannelKind
    config: dict[str, str]

    @field_validator("config")
    @classmethod
    def _valid(cls, v: dict[str, str], info: Any) -> dict[str, str]:
        kind = info.data.get("kind")
        if kind is None:
            return v
        return CHANNEL_CONFIG[kind].model_validate(v).model_dump()


class Channel(ChannelDraft):
    id: str
    created_at: datetime

    def hint(self) -> str:
        """Where it goes, without its secret: the host, the chat, the address."""
        c = self.config
        if self.kind is ChannelKind.TELEGRAM:
            return f"chat {c.get('chat_id', '?')}"
        if self.kind is ChannelKind.EMAIL:
            return c.get("to", "?")
        url = c.get("url", "")
        return url.split("/")[2] if url.count("/") >= 2 else "?"


class Delivery(DomainModel):
    channel_id: str
    channel_name: str
    ok: bool
    error: str | None = None


class Candidate(DomainModel):
    key: str = Field(description="Same fact, same key: fires once per rule")
    title: str
    detail: str = ""
    severity: Severity = Severity.INFO
    source: str
    url: str | None = None
    lat: float | None = None
    lon: float | None = None
    layer: str | None = Field(default=None, description="Map layer that shows it")
    unverified: bool = False


class Alert(Candidate):
    id: str
    rule_id: str
    rule_name: str
    at: datetime
    read: bool = False
    deliveries: tuple[Delivery, ...] = ()


# ── Snapshot and evaluators ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Snapshot:
    """What the feeds say now. A field is None when no rule needed it."""

    now: datetime
    earthquakes: list[GeoEvent] | None = None
    disasters: list[GeoEvent] | None = None
    stories: list[Story] | None = None
    quotes: list[Quote] | None = None
    signals: list[CountrySignal] | None = None
    convergences: list[Convergence] | None = None
    tracks: dict[str, AircraftTrack | None] = field(default_factory=dict)
    digest: tuple[str, list[str]] | None = None  # (text, facts), when a digest rule is due


def _in(countries: tuple[str, ...], iso2: object) -> bool:
    return not countries or (isinstance(iso2, str) and iso2 in countries)


def earthquakes(p: EarthquakeParams, s: Snapshot) -> list[Candidate]:
    out = []
    for e in s.earthquakes or []:
        if (e.magnitude or 0) < p.min_magnitude or not _in(
            p.countries, e.details.get("country_iso2")
        ):
            continue
        # USGS titles already start with the magnitude ("M 6.1 - 48 km SSE of …").
        title = e.title if e.title.startswith("M ") else f"M {e.magnitude} · {e.title}"
        out.append(
            Candidate(
                key=f"eq:{e.id}", title=title, source="USGS",
                severity=Severity.CRITICAL if (e.magnitude or 0) >= 7 else Severity.WARNING,
                url=e.url, lat=e.position.lat, lon=e.position.lon, layer="earthquakes",
                detail=f"Occurred {e.occurred_at.isoformat(timespec='minutes')}",
            )
        )  # fmt: skip
    return out


LEVELS = {"orange": 1, "red": 2}


def disasters(p: DisasterParams, s: Snapshot) -> list[Candidate]:
    out = []
    for e in s.disasters or []:
        level = str(e.details.get("alert_level") or "")
        if LEVELS.get(level, 0) < LEVELS[p.min_level] or not _in(
            p.countries, e.details.get("country_iso2")
        ):
            continue
        out.append(
            Candidate(
                key=f"gdacs:{e.id}:{level}", title=f"{level.title()} alert · {e.title}",
                source="GDACS", severity=Severity.CRITICAL if level == "red" else Severity.WARNING,
                url=e.url, lat=e.position.lat, lon=e.position.lon, layer="disaster-alerts",
            )
        )  # fmt: skip
    return out


def keywords(p: KeywordParams, s: Snapshot) -> list[Candidate]:
    out = []
    for story in s.stories or []:
        text = story.title.casefold()
        for kw in p.keywords:
            if kw in text and len(story.sources) >= p.min_outlets:
                outlets = ", ".join(src.name for src in story.sources[:3])
                out.append(
                    Candidate(
                        key=f"kw:{kw}:{story.id}", title=story.title, source=outlets,
                        detail=f"Matches “{kw}” · {len(story.sources)} outlet(s)",
                        url=story.url, unverified=story.state_media_only,
                    )
                )  # fmt: skip
                break
    return out


def ticker_moves(p: TickerParams, s: Snapshot) -> list[Candidate]:
    out = []
    day = s.now.date().isoformat()
    for q in s.quotes or []:
        pct = q.change_pct
        if pct is None or abs(pct) < p.min_change_pct:
            continue
        if p.symbols and q.instrument.symbol not in p.symbols:
            continue
        direction = "up" if pct > 0 else "down"
        out.append(
            Candidate(
                key=f"tk:{q.instrument.symbol}:{day}:{direction}",
                title=f"{q.instrument.name} {pct:+.2f} %", source=f"{q.source} (delayed)",
                detail=f"{q.price} {q.instrument.unit or q.currency or ''}".strip(),
                severity=Severity.WARNING,
            )
        )  # fmt: skip
    return out


def country_scores(p: CountryScoreParams, s: Snapshot) -> list[Candidate]:
    day = s.now.date().isoformat()
    return [
        Candidate(
            key=f"cs:{c.iso2}:{day}", title=f"{c.name}: signal index {c.score:.0f}",
            source="Argus signal index",
            detail="Disruptive activity reported now, not a stability measure",
            severity=Severity.WARNING, layer="country-index",
        )
        for c in s.signals or []
        if c.score >= p.min_score and _in(p.countries, c.iso2)
    ]  # fmt: skip


def convergences(p: ConvergenceParams, s: Snapshot) -> list[Candidate]:
    out = []
    day = s.now.date().isoformat()
    for c in s.convergences or []:
        verified = [k for k in c.kinds if k.kind.value not in UNVERIFIED_KINDS]
        if len(verified) < p.min_verified_kinds or not _in(p.countries, c.country):
            continue
        kinds = ", ".join(f"{k.kind.value.replace('_', ' ')} x{k.count}" for k in c.kinds)
        where = f" in {c.country}" if c.country else ""
        out.append(
            Candidate(
                key=f"cv:{c.id}:{day}", title=f"Signals converge{where}",
                detail=kinds, source="Argus convergence", severity=Severity.WARNING,
                lat=c.center.lat, lon=c.center.lon, layer="convergence",
            )
        )  # fmt: skip
    return out


def watched_aircraft(p: AircraftParams, s: Snapshot) -> list[Candidate]:
    out = []
    day = s.now.date().isoformat()
    for icao24 in p.icao24:
        track = s.tracks.get(icao24)
        last = track.points[-1] if track and track.points else None
        if last is None or (s.now - last.at).total_seconds() > SEEN_WITHIN_S:
            continue
        name = track.callsign if track and track.callsign else icao24
        out.append(
            Candidate(
                key=f"ac:{icao24}:{day}", title=f"{name} is flying",
                source=track.source if track else "",
                detail=f"Seen at {last.at.isoformat(timespec='minutes')}"
                + (f", {round(last.altitude_m)} m" if last.altitude_m is not None else ""),
                lat=last.position.lat, lon=last.position.lon, layer="aircraft",
            )
        )  # fmt: skip
    return out


def digest(p: DigestParams, s: Snapshot) -> list[Candidate]:
    if s.digest is None or s.now.hour < p.hour_utc:
        return []
    text, _facts = s.digest
    return [
        Candidate(
            key=f"digest:{s.now.date().isoformat()}",
            title="Daily digest",
            detail=text,
            source="Argus (figures computed by Argus)",
        )
    ]


EVALUATORS: dict[RuleKind, Callable[[Any, Snapshot], list[Candidate]]] = {
    RuleKind.WATCHED_AIRCRAFT: watched_aircraft,
    RuleKind.EARTHQUAKE: earthquakes,
    RuleKind.DISASTER_ALERT: disasters,
    RuleKind.KEYWORD: keywords,
    RuleKind.TICKER_MOVE: ticker_moves,
    RuleKind.COUNTRY_SCORE: country_scores,
    RuleKind.CONVERGENCE: convergences,
    RuleKind.DAILY_DIGEST: digest,
}


def evaluate(rule: Rule, snapshot: Snapshot) -> list[Candidate]:
    return EVALUATORS[rule.kind](parse_params(rule.kind, rule.params), snapshot)


def digest_due(rules: Sequence[Rule], now: datetime) -> bool:
    return any(
        r.enabled and r.kind is RuleKind.DAILY_DIGEST and now.hour >= r.params.get("hour_utc", 7)
        for r in rules
    )


# ── Ports ──────────────────────────────────────────────────────────────────


class AlertRepository(Protocol):
    async def rules(self, owner: str) -> list[Rule]: ...
    async def owners(self) -> list[str]: ...
    async def save_rule(self, owner: str, rule: Rule) -> Rule: ...
    async def delete_rule(self, owner: str, rule_id: str) -> bool: ...
    async def channels(self, owner: str) -> list[Channel]: ...
    async def save_channel(self, owner: str, channel: Channel) -> Channel: ...
    async def delete_channel(self, owner: str, channel_id: str) -> bool: ...
    async def seen(self, owner: str, rule_id: str, key: str) -> bool: ...
    async def add_alert(self, owner: str, alert: Alert) -> None: ...
    async def alerts(self, owner: str, limit: int, unread_only: bool) -> list[Alert]: ...
    async def unread(self, owner: str) -> int: ...
    async def mark_read(self, owner: str, ids: Sequence[str] | None) -> int: ...


class Notifier(Protocol):
    """Delivers one alert to one channel. Raises ProviderError when it cannot."""

    async def send(self, channel: Channel, alert: Alert) -> None: ...
