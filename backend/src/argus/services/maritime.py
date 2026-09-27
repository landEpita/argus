"""Vessels. The relay's store is already in memory, so there is no extra cache."""

from __future__ import annotations

from dataclasses import dataclass

from argus.domain.maritime import VESSEL_POSITIONS, Vessel, VesselQuery
from argus.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class VesselPage:
    items: list[Vessel]
    truncated: bool


class MaritimeService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    async def vessels(self, query: VesselQuery, limit: int) -> VesselPage:
        vessels = await self._registry.fetch(VESSEL_POSITIONS, query)
        vessels.sort(key=lambda v: v.last_seen, reverse=True)
        return VesselPage(items=vessels[:limit], truncated=len(vessels) > limit)
