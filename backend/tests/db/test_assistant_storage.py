from datetime import UTC, datetime, timedelta

from argus.domain.llm import StoredLlmSettings, UsageRecord
from argus.infra.db import Database
from argus.infra.db.repositories import SqlLlmSettingsRepository, SqlUsageRepository

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


def record(owner: str, model: str, cost: float | None, days_ago: int = 0) -> UsageRecord:
    return UsageRecord(
        owner=owner, at=NOW - timedelta(days=days_ago), purpose="ask", provider="llm",
        model=model, input_tokens=100, output_tokens=20, cost_usd=cost,
    )  # fmt: skip


async def test_settings_round_trip_per_owner(database: Database) -> None:
    repo = SqlLlmSettingsRepository(database)
    assert await repo.get("alice") is None
    await repo.save(
        "alice", StoredLlmSettings(model="ollama/mistral", api_key=None, api_base="http://x")
    )
    await repo.save(
        "alice", StoredLlmSettings(model="anthropic/claude-sonnet-5", api_key="k", api_base=None)
    )
    assert await repo.get("alice") == StoredLlmSettings(
        model="anthropic/claude-sonnet-5", api_key="k", api_base=None
    )
    assert await repo.get("bob") is None


async def test_usage_is_summed_per_model_over_the_window(database: Database) -> None:
    repo = SqlUsageRepository(database)
    for r in (
        record("alice", "anthropic/claude-sonnet-5", 0.002),
        record("alice", "anthropic/claude-sonnet-5", 0.003),
        record("alice", "ollama/mistral", 0.0),
        record("alice", "custom/unknown", None),
        record("alice", "ollama/mistral", 0.0, days_ago=40),
        record("bob", "ollama/mistral", 0.0),
    ):
        await repo.add(r)
    rows = {r.model: r for r in await repo.summary("alice", NOW - timedelta(days=30))}
    assert set(rows) == {"anthropic/claude-sonnet-5", "ollama/mistral", "custom/unknown"}
    sonnet = rows["anthropic/claude-sonnet-5"]
    assert (sonnet.calls, sonnet.input_tokens, sonnet.output_tokens) == (2, 200, 40)
    assert sonnet.cost_usd == 0.005
    assert rows["ollama/mistral"].calls == 1
    assert rows["custom/unknown"].calls_without_cost == 1
