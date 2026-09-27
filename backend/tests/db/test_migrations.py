"""The migrations are the schema: they must build it and match the ORM exactly."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from argus.infra.db.tables import Base

BACKEND = Path(__file__).parents[2]


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture
def sqlite_file(tmp_path: Path) -> tuple[str, str]:
    path = tmp_path / "migrations.db"
    return f"sqlite+aiosqlite:///{path}", f"sqlite:///{path}"


def test_upgrade_builds_a_schema_identical_to_the_models(sqlite_file: tuple[str, str]) -> None:
    async_url, sync_url = sqlite_file
    command.upgrade(alembic_config(async_url), "head")

    engine = create_engine(sync_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"models and migrations disagree; run `make migration`: {diff}"


def test_downgrade_to_base_removes_everything(sqlite_file: tuple[str, str]) -> None:
    async_url, sync_url = sqlite_file
    config = alembic_config(async_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(sync_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert tables == {"alembic_version"}
