from uuid import uuid4

import pytest

from argus.domain.errors import ConflictError
from argus.domain.geo import GeoPoint
from argus.domain.preferences import Preferences, Viewport
from argus.domain.watchlist import WatchItem, WatchKind, WatchlistDraft
from argus.infra.db import Database
from argus.infra.db.repositories import SqlPreferencesRepository, SqlWatchlistRepository

ALICE, BOB = "alice", "bob"


def draft(name: str = "Gulf", *values: str) -> WatchlistDraft:
    return WatchlistDraft(
        name=name,
        items=tuple(WatchItem(kind=WatchKind.AIRCRAFT, value=v, label=f"#{v}") for v in values),
    )


@pytest.fixture
def watchlists(database: Database) -> SqlWatchlistRepository:
    return SqlWatchlistRepository(database)


@pytest.fixture
def preferences(database: Database) -> SqlPreferencesRepository:
    return SqlPreferencesRepository(database)


class TestWatchlists:
    async def test_create_then_get_round_trips_items_in_order(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        created = await watchlists.create(ALICE, draft("Gulf", "ffffff", "aaaaaa", "cccccc"))
        fetched = await watchlists.get(ALICE, created.id)
        assert fetched == created
        assert [i.value for i in created.items] == ["ffffff", "aaaaaa", "cccccc"]
        assert created.items[0].label == "#ffffff"
        assert created.created_at.tzinfo is not None

    async def test_list_is_scoped_to_owner_and_sorted(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        await watchlists.create(ALICE, draft("Zulu"))
        await watchlists.create(ALICE, draft("Alpha"))
        await watchlists.create(BOB, draft("Bravo"))
        assert [w.name for w in await watchlists.list(ALICE)] == ["Alpha", "Zulu"]
        assert await watchlists.count(ALICE) == 2
        assert await watchlists.count("nobody") == 0

    async def test_names_are_unique_per_owner_only(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        await watchlists.create(ALICE, draft("Gulf"))
        await watchlists.create(BOB, draft("Gulf"))
        with pytest.raises(ConflictError, match="already exists"):
            await watchlists.create(ALICE, draft("Gulf"))

    async def test_other_owners_lists_are_invisible(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        mine = await watchlists.create(ALICE, draft("Gulf"))
        assert await watchlists.get(BOB, mine.id) is None
        assert await watchlists.replace(BOB, mine.id, draft("Hijack")) is None
        assert await watchlists.delete(BOB, mine.id) is False
        assert await watchlists.get(ALICE, mine.id) is not None

    async def test_replace_swaps_name_and_items_keeping_overlap(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        created = await watchlists.create(ALICE, draft("Gulf", "aaaaaa", "bbbbbb"))
        replaced = await watchlists.replace(ALICE, created.id, draft("Red Sea", "bbbbbb", "cccccc"))
        assert replaced is not None
        assert replaced.id == created.id
        assert replaced.name == "Red Sea"
        assert [i.value for i in replaced.items] == ["bbbbbb", "cccccc"]
        assert replaced.updated_at >= created.updated_at
        assert replaced.created_at == created.created_at

    async def test_replace_to_a_taken_name_conflicts(
        self, watchlists: SqlWatchlistRepository
    ) -> None:
        await watchlists.create(ALICE, draft("Gulf"))
        other = await watchlists.create(ALICE, draft("Red Sea"))
        with pytest.raises(ConflictError):
            await watchlists.replace(ALICE, other.id, draft("Gulf"))

    async def test_replace_missing_returns_none(self, watchlists: SqlWatchlistRepository) -> None:
        assert await watchlists.replace(ALICE, uuid4(), draft()) is None

    async def test_delete_removes_items_too(
        self, watchlists: SqlWatchlistRepository, database: Database
    ) -> None:
        created = await watchlists.create(ALICE, draft("Gulf", "aaaaaa"))
        assert await watchlists.delete(ALICE, created.id) is True
        assert await watchlists.get(ALICE, created.id) is None
        assert await watchlists.delete(ALICE, created.id) is False
        # A new list may reuse the name and the same items.
        await watchlists.create(ALICE, draft("Gulf", "aaaaaa"))


class TestPreferences:
    async def test_missing_is_none(self, preferences: SqlPreferencesRepository) -> None:
        assert await preferences.get(ALICE) is None

    async def test_save_then_update(self, preferences: SqlPreferencesRepository) -> None:
        first = Preferences(enabled_layers=("aircraft",))
        saved = await preferences.save(ALICE, first)
        assert saved.preferences == first
        assert saved.updated_at is not None

        second = Preferences(
            enabled_layers=(), viewport=Viewport(center=GeoPoint(lat=48.8, lon=2.3), zoom=6)
        )
        await preferences.save(ALICE, second)
        stored = await preferences.get(ALICE)
        assert stored is not None
        assert stored.preferences == second
        assert await preferences.get(BOB) is None
