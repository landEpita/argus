from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from argus.api.deps import OwnerDep, WatchlistServiceDep
from argus.domain.watchlist import Watchlist, WatchlistDraft

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[Watchlist])
async def list_watchlists(service: WatchlistServiceDep, owner: OwnerDep) -> list[Watchlist]:
    return await service.list(owner)


@router.post("", response_model=Watchlist, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    draft: WatchlistDraft, service: WatchlistServiceDep, owner: OwnerDep
) -> Watchlist:
    return await service.create(owner, draft)


@router.get("/{watchlist_id}", response_model=Watchlist)
async def get_watchlist(
    watchlist_id: UUID, service: WatchlistServiceDep, owner: OwnerDep
) -> Watchlist:
    return await service.get(owner, watchlist_id)


@router.put("/{watchlist_id}", response_model=Watchlist)
async def replace_watchlist(
    watchlist_id: UUID, draft: WatchlistDraft, service: WatchlistServiceDep, owner: OwnerDep
) -> Watchlist:
    return await service.replace(owner, watchlist_id, draft)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID, service: WatchlistServiceDep, owner: OwnerDep
) -> Response:
    await service.delete(owner, watchlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
