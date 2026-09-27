"""Watchlist use cases: quota and not-found rules on top of the repository."""

from __future__ import annotations

from uuid import UUID

from argus.domain.errors import LimitExceededError, NotFoundError
from argus.domain.watchlist import (
    MAX_WATCHLISTS_PER_OWNER,
    Watchlist,
    WatchlistDraft,
    WatchlistRepository,
)


class WatchlistService:
    def __init__(self, repository: WatchlistRepository) -> None:
        self._repo = repository

    async def list(self, owner: str) -> list[Watchlist]:
        return await self._repo.list(owner)

    async def get(self, owner: str, watchlist_id: UUID) -> Watchlist:
        found = await self._repo.get(owner, watchlist_id)
        if found is None:
            raise NotFoundError("watchlist", watchlist_id)
        return found

    async def create(self, owner: str, draft: WatchlistDraft) -> Watchlist:
        if await self._repo.count(owner) >= MAX_WATCHLISTS_PER_OWNER:
            raise LimitExceededError(f"at most {MAX_WATCHLISTS_PER_OWNER} watchlists per owner")
        return await self._repo.create(owner, draft)

    async def replace(self, owner: str, watchlist_id: UUID, draft: WatchlistDraft) -> Watchlist:
        updated = await self._repo.replace(owner, watchlist_id, draft)
        if updated is None:
            raise NotFoundError("watchlist", watchlist_id)
        return updated

    async def delete(self, owner: str, watchlist_id: UUID) -> None:
        if not await self._repo.delete(owner, watchlist_id):
            raise NotFoundError("watchlist", watchlist_id)
