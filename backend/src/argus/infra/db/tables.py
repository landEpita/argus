"""ORM tables. Only the repositories in this package import them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Deterministic constraint names, so migrations are reproducible across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class WatchlistRow(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    items: Mapped[list[WatchlistItemRow]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItemRow.position",
        lazy="selectin",
    )


class WatchlistItemRow(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "kind", "value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)

    watchlist: Mapped[WatchlistRow] = relationship(back_populates="items")


class PreferencesRow(Base):
    __tablename__ = "preferences"

    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class SignalSnapshotRow(Base):
    __tablename__ = "country_signal_snapshots"
    __table_args__ = (Index("ix_country_signal_snapshots_iso2_taken_at", "iso2", "taken_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iso2: Mapped[str] = mapped_column(String(2))
    score: Mapped[float] = mapped_column(Float)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    taken_at: Mapped[datetime] = mapped_column(index=True)


class AssistantSettingsRow(Base):
    """The model an owner chose in the app. The key stays in this table, server side."""

    __tablename__ = "assistant_settings"

    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str | None] = mapped_column(String(200))
    api_key: Mapped[str | None] = mapped_column(String(500))
    api_base: Mapped[str | None] = mapped_column(String(500))
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class LlmUsageRow(Base):
    """One model call: what it cost, for the owner's usage summary."""

    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_owner_at", "owner_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column()
    purpose: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)


class AlertRuleRow(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    channels: Mapped[list[str]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_fired_at: Mapped[datetime | None] = mapped_column()


class AlertChannelRow(Base):
    """Where alerts go. `config` holds the channel's secret (webhook URL, bot token)."""

    __tablename__ = "alert_channels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict[str, str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AlertRow(Base):
    """A fired alert. One per (owner, rule, dedupe key): the same fact fires once."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("owner_id", "rule_id", "dedupe_key"),
        Index("ix_alerts_owner_at", "owner_id", "at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(32))
    rule_name: Mapped[str] = mapped_column(String(100))
    dedupe_key: Mapped[str] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column()
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    layer: Mapped[str | None] = mapped_column(String(40))
    unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    deliveries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class AlertSettingsRow(Base):
    __tablename__ = "alert_settings"

    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class ServerSecretRow(Base):
    """Secrets the server generates for itself (the Web Push VAPID key)."""

    __tablename__ = "server_secrets"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
