"""SQLAlchemy implementations of the domain repository ports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from argus.domain.errors import ConflictError
from argus.domain.llm import ModelUsage, StoredLlmSettings, UsageRecord
from argus.domain.preferences import Preferences, StoredPreferences
from argus.domain.signal_index import Component, CountrySignal, HistoryPoint
from argus.domain.watchlist import WatchItem, WatchKind, Watchlist, WatchlistDraft
from argus.infra.db.database import Database
from argus.infra.db.tables import (
    AssistantSettingsRow,
    LlmUsageRow,
    PreferencesRow,
    SignalSnapshotRow,
    WatchlistItemRow,
    WatchlistRow,
    utcnow,
)


def _aware(value: datetime) -> datetime:
    """SQLite drops tzinfo on the way back; every timestamp we write is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _to_domain(row: WatchlistRow) -> Watchlist:
    return Watchlist(
        id=row.id,
        name=row.name,
        items=tuple(
            WatchItem(kind=WatchKind(i.kind), value=i.value, label=i.label) for i in row.items
        ),
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _item_rows(draft: WatchlistDraft) -> list[WatchlistItemRow]:
    return [
        WatchlistItemRow(kind=item.kind.value, value=item.value, label=item.label, position=index)
        for index, item in enumerate(draft.items)
    ]


class SqlWatchlistRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list(self, owner: str) -> list[Watchlist]:
        async with self._db.transaction() as session:
            rows = await session.scalars(
                select(WatchlistRow)
                .where(WatchlistRow.owner_id == owner)
                .order_by(WatchlistRow.name)
            )
            return [_to_domain(row) for row in rows]

    async def count(self, owner: str) -> int:
        async with self._db.transaction() as session:
            total = await session.scalar(
                select(func.count()).select_from(WatchlistRow).where(WatchlistRow.owner_id == owner)
            )
            return int(total or 0)

    async def get(self, owner: str, watchlist_id: UUID) -> Watchlist | None:
        async with self._db.transaction() as session:
            row = await self._owned(session, owner, watchlist_id)
            return _to_domain(row) if row else None

    async def create(self, owner: str, draft: WatchlistDraft) -> Watchlist:
        row = WatchlistRow(owner_id=owner, name=draft.name, items=_item_rows(draft))
        try:
            async with self._db.transaction() as session:
                session.add(row)
                await session.flush()
                await session.refresh(row, ["items"])
                return _to_domain(row)
        except IntegrityError as exc:
            raise ConflictError(f"a watchlist named '{draft.name}' already exists") from exc

    async def replace(
        self, owner: str, watchlist_id: UUID, draft: WatchlistDraft
    ) -> Watchlist | None:
        try:
            async with self._db.transaction() as session:
                row = await self._owned(session, owner, watchlist_id)
                if row is None:
                    return None
                row.name = draft.name
                row.updated_at = utcnow()
                # Clear and flush first: re-adding an item with the same (kind, value)
                # would otherwise hit the unique constraint before the delete runs.
                row.items.clear()
                await session.flush()
                row.items.extend(_item_rows(draft))
                await session.flush()
                await session.refresh(row, ["items"])
                return _to_domain(row)
        except IntegrityError as exc:
            raise ConflictError(f"a watchlist named '{draft.name}' already exists") from exc

    async def delete(self, owner: str, watchlist_id: UUID) -> bool:
        async with self._db.transaction() as session:
            row = await self._owned(session, owner, watchlist_id)
            if row is None:
                return False
            await session.delete(row)
            return True

    @staticmethod
    async def _owned(session: AsyncSession, owner: str, watchlist_id: UUID) -> WatchlistRow | None:
        row = await session.get(WatchlistRow, watchlist_id)
        # Another owner's list is reported as missing, never as forbidden:
        # its existence is not ours to reveal.
        return row if row is not None and row.owner_id == owner else None


class SqlPreferencesRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, owner: str) -> StoredPreferences | None:
        async with self._db.transaction() as session:
            row = await session.get(PreferencesRow, owner)
            if row is None:
                return None
            return StoredPreferences(
                preferences=Preferences.model_validate(row.data),
                updated_at=_aware(row.updated_at),
            )

    async def save(self, owner: str, preferences: Preferences) -> StoredPreferences:
        data = preferences.model_dump(mode="json")
        async with self._db.transaction() as session:
            row = await session.get(PreferencesRow, owner)
            if row is None:
                row = PreferencesRow(owner_id=owner, data=data)
                session.add(row)
            else:
                row.data = data
                row.updated_at = utcnow()
            await session.flush()
            return StoredPreferences(preferences=preferences, updated_at=_aware(row.updated_at))


class SqlSignalHistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, signals: Sequence[CountrySignal], at: datetime) -> None:
        async with self._db.transaction() as session:
            session.add_all(
                SignalSnapshotRow(
                    iso2=s.iso2,
                    score=s.score,
                    raw={c.component.value: c.raw for c in s.components},
                    taken_at=at,
                )
                for s in signals
            )

    async def history(self, iso2: str, since: datetime) -> list[HistoryPoint]:
        async with self._db.transaction() as session:
            rows = await session.scalars(
                select(SignalSnapshotRow)
                .where(SignalSnapshotRow.iso2 == iso2.upper(), SignalSnapshotRow.taken_at >= since)
                .order_by(SignalSnapshotRow.taken_at)
            )
            return [
                HistoryPoint(at=_aware(r.taken_at), score=r.score, raw=_raw(r.raw)) for r in rows
            ]

    async def samples(self, since: datetime) -> list[tuple[str, dict[Component, float]]]:
        async with self._db.transaction() as session:
            rows = await session.execute(
                select(SignalSnapshotRow.iso2, SignalSnapshotRow.raw).where(
                    SignalSnapshotRow.taken_at >= since
                )
            )
            return [(iso2, _raw(raw)) for iso2, raw in rows]

    async def prune(self, before: datetime) -> int:
        async with self._db.transaction() as session:
            result = await session.execute(
                delete(SignalSnapshotRow).where(SignalSnapshotRow.taken_at < before)
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _raw(stored: object) -> dict[Component, float]:
    """Stored component values; unknown keys (a renamed component) are ignored."""
    if not isinstance(stored, dict):
        return {}
    known = {c.value: c for c in Component}
    return {
        known[k]: float(v)
        for k, v in stored.items()
        if k in known and isinstance(v, int | float) and not isinstance(v, bool)
    }


class SqlLlmSettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, owner: str) -> StoredLlmSettings | None:
        async with self._db.transaction() as session:
            row = await session.get(AssistantSettingsRow, owner)
            if row is None:
                return None
            return StoredLlmSettings(
                model=row.model,
                api_key=row.api_key,
                api_base=row.api_base,
                embedding_model=row.embedding_model,
            )

    async def save(self, owner: str, settings: StoredLlmSettings) -> None:
        async with self._db.transaction() as session:
            row = await session.get(AssistantSettingsRow, owner)
            if row is None:
                session.add(AssistantSettingsRow(owner_id=owner, **settings.model_dump()))
            else:
                row.model = settings.model
                row.api_key = settings.api_key
                row.api_base = settings.api_base
                row.embedding_model = settings.embedding_model
                row.updated_at = utcnow()


class SqlUsageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, record: UsageRecord) -> None:
        data = record.model_dump()
        async with self._db.transaction() as session:
            session.add(LlmUsageRow(owner_id=data.pop("owner"), **data))

    async def summary(self, owner: str, since: datetime) -> list[ModelUsage]:
        stmt = (
            select(
                LlmUsageRow.model,
                func.count(),
                func.coalesce(func.sum(LlmUsageRow.input_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.output_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.cost_usd), 0.0),
                func.count() - func.count(LlmUsageRow.cost_usd),
            )
            .where(LlmUsageRow.owner_id == owner, LlmUsageRow.at >= since)
            .group_by(LlmUsageRow.model)
            .order_by(func.count().desc())
        )
        async with self._db.transaction() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ModelUsage(
                model=m, calls=n, input_tokens=int(i or 0), output_tokens=int(o or 0),
                cost_usd=round(float(c or 0), 6), calls_without_cost=int(u or 0),
            )
            for m, n, i, o, c, u in rows
        ]  # fmt: skip
