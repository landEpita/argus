"""
Shared fixtures.

``database`` runs every repository test against SQLite and, when
``ARGUS_TEST_DATABASE_URL`` points at a Postgres server (as in CI), against
Postgres too. ``ARGUS_TEST_REDIS_URL`` does the same for the Redis cache.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from argus.config import Settings
from argus.infra.db import Database
from argus.infra.db.tables import Base

SQLITE_MEMORY = "sqlite+aiosqlite://"
POSTGRES_URL = os.environ.get("ARGUS_TEST_DATABASE_URL")
REDIS_URL = os.environ.get("ARGUS_TEST_REDIS_URL")

DATABASE_URLS = [pytest.param(SQLITE_MEMORY, id="sqlite")]
if POSTGRES_URL:
    DATABASE_URLS.append(pytest.param(POSTGRES_URL, id="postgres"))


PROVIDER_SWITCHES = (
    "opensky_enabled",
    "assistant_enabled",
    "alerts_enabled",
    "liquidations_enabled",
    "eia_enabled",
    "adsblol_enabled",
    "usgs_enabled",
    "eonet_enabled",
    "gdacs_enabled",
    "gdelt_enabled",
    "celestrak_enabled",
    "ukraine_alerts_enabled",
    "launchlibrary_enabled",
    "overpass_enabled",
    "telegeography_enabled",
    "rainviewer_enabled",
    "cameras_enabled",
    "news_enabled",
    "cisa_kev_enabled",
    "ioda_enabled",
    "telegram_enabled",
    "yahoo_enabled",
    "coingecko_enabled",
    "funding_enabled",
    "polymarket_enabled",
    "macro_enabled",
    "portwatch_enabled",
)


def offline_settings(**overrides: object) -> Settings:
    """Settings with every real upstream switched off and an in-memory database."""
    values: dict[str, object] = {name: False for name in PROVIDER_SWITCHES}
    values |= {"database_url": SQLITE_MEMORY, "firms_map_key": None, "aisstream_api_key": None}
    values |= overrides
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


async def reset_schema(db: Database) -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(params=DATABASE_URLS)
async def database(request: pytest.FixtureRequest) -> AsyncIterator[Database]:
    db = Database(request.param)
    await reset_schema(db)
    yield db
    await db.aclose()
