"""
Async SQLAlchemy engine and transactional sessions.

Postgres in production (``postgresql+asyncpg://``); SQLite for local
development and tests (``sqlite+aiosqlite://``). The schema only uses portable
types so the same Alembic migrations run on both.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        options: dict[str, Any] = {"echo": echo}
        if url.startswith("sqlite"):
            if url in {"sqlite+aiosqlite://", "sqlite+aiosqlite:///:memory:"}:
                # One shared connection, or every session would see its own empty DB.
                options["poolclass"] = StaticPool
                options["connect_args"] = {"check_same_thread": False}
        else:
            options["pool_pre_ping"] = True
        self.engine: AsyncEngine = create_async_engine(url, **options)
        if url.startswith("sqlite"):
            event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """A session inside one transaction: committed on success, rolled back on error."""
        async with self._sessions() as session, session.begin():
            yield session

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def aclose(self) -> None:
        await self.engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
