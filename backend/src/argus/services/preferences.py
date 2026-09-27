from __future__ import annotations

from argus.domain.preferences import Preferences, PreferencesRepository, StoredPreferences


class PreferencesService:
    def __init__(self, repository: PreferencesRepository) -> None:
        self._repo = repository

    async def get(self, owner: str) -> StoredPreferences:
        """Stored preferences, or defaults (``updated_at=None``) if never saved."""
        stored = await self._repo.get(owner)
        return stored or StoredPreferences(preferences=Preferences(), updated_at=None)

    async def save(self, owner: str, preferences: Preferences) -> StoredPreferences:
        return await self._repo.save(owner, preferences)
