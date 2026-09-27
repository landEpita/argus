from __future__ import annotations

from fastapi import APIRouter

from argus.api.deps import OwnerDep, PreferencesServiceDep
from argus.domain.preferences import Preferences, StoredPreferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=StoredPreferences)
async def get_preferences(service: PreferencesServiceDep, owner: OwnerDep) -> StoredPreferences:
    return await service.get(owner)


@router.put("", response_model=StoredPreferences)
async def save_preferences(
    preferences: Preferences, service: PreferencesServiceDep, owner: OwnerDep
) -> StoredPreferences:
    return await service.save(owner, preferences)
