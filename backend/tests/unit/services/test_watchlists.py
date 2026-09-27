from uuid import uuid4

import pytest

from argus.domain.errors import LimitExceededError, NotFoundError
from argus.domain.watchlist import MAX_WATCHLISTS_PER_OWNER, WatchlistDraft
from argus.infra.db import Database
from argus.infra.db.repositories import SqlPreferencesRepository, SqlWatchlistRepository
from argus.services.preferences import PreferencesService
from argus.services.watchlists import WatchlistService


@pytest.fixture
def service(database: Database) -> WatchlistService:
    return WatchlistService(SqlWatchlistRepository(database))


async def test_missing_watchlist_raises_not_found(service: WatchlistService) -> None:
    missing = uuid4()
    with pytest.raises(NotFoundError, match=str(missing)):
        await service.get("local", missing)
    with pytest.raises(NotFoundError):
        await service.replace("local", missing, WatchlistDraft(name="x"))
    with pytest.raises(NotFoundError):
        await service.delete("local", missing)


async def test_quota_per_owner(service: WatchlistService) -> None:
    for i in range(MAX_WATCHLISTS_PER_OWNER):
        await service.create("local", WatchlistDraft(name=f"list {i}"))
    with pytest.raises(LimitExceededError):
        await service.create("local", WatchlistDraft(name="one too many"))
    await service.create("someone-else", WatchlistDraft(name="fine"))


async def test_crud_round_trip(service: WatchlistService) -> None:
    created = await service.create("local", WatchlistDraft(name="a"))
    assert await service.get("local", created.id) == created
    assert [w.id for w in await service.list("local")] == [created.id]
    renamed = await service.replace("local", created.id, WatchlistDraft(name="b"))
    assert renamed.name == "b"
    await service.delete("local", created.id)
    assert await service.list("local") == []


async def test_preferences_default_until_saved(database: Database) -> None:
    service = PreferencesService(SqlPreferencesRepository(database))
    default = await service.get("local")
    assert default.updated_at is None
    assert default.preferences.enabled_layers is None
    await service.save("local", default.preferences.model_copy(update={"enabled_layers": ()}))
    assert (await service.get("local")).preferences.enabled_layers == ()
