from datetime import UTC, datetime, timedelta

from argus.domain.signal_index import Component, ComponentScore, CountrySignal
from argus.infra.db import Database
from argus.infra.db.repositories import SqlSignalHistoryRepository

T0 = datetime(2026, 9, 20, tzinfo=UTC)


def signal(iso2: str, score: float) -> CountrySignal:
    component = ComponentScore(
        component=Component.AIR_ALERTS, raw=score / 10, points=0, max_points=15, rule="r"
    )
    return CountrySignal(iso2=iso2, name=iso2, score=score, components=(component,), computed_at=T0)


async def test_save_history_and_prune(database: Database) -> None:
    repo = SqlSignalHistoryRepository(database)
    for day in range(5):
        await repo.save([signal("UA", 50 + day), signal("IR", 10)], T0 + timedelta(days=day))
    history = await repo.history("ua", T0 + timedelta(days=2))
    assert [p.score for p in history] == [52, 53, 54]
    assert history[0].at == T0 + timedelta(days=2)
    assert await repo.prune(T0 + timedelta(days=3)) == 6
    assert len(await repo.history("UA", T0)) == 2


async def test_samples_carry_raw_component_values(database: Database) -> None:
    repo = SqlSignalHistoryRepository(database)
    await repo.save([signal("UA", 50), signal("IR", 20)], T0)
    samples = sorted(await repo.samples(T0 - timedelta(days=1)))
    assert samples == [("IR", {Component.AIR_ALERTS: 2.0}), ("UA", {Component.AIR_ALERTS: 5.0})]
    [point] = await repo.history("UA", T0)
    assert point.raw == {Component.AIR_ALERTS: 5.0}


def test_unknown_stored_keys_are_ignored() -> None:
    from argus.infra.db.repositories import _raw

    assert _raw({"air_alerts": 1, "renamed_component": 3, "news_attention": True}) == {
        Component.AIR_ALERTS: 1.0
    }
    assert _raw(None) == {}
