from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from argus.api.deps import SpaceServiceDep
from argus.domain.space import SatelliteGroup, SatellitePosition

router = APIRouter(prefix="/space", tags=["space"])


class SatelliteCollection(BaseModel):
    group: SatelliteGroup
    count: int
    items: list[SatellitePosition]


@router.get("/satellites", response_model=SatelliteCollection)
async def list_satellites(
    service: SpaceServiceDep, group: SatelliteGroup = SatelliteGroup.STATIONS
) -> SatelliteCollection:
    """Positions now, propagated with SGP4 from CelesTrak elements."""
    items = await service.positions(group)
    return SatelliteCollection(group=group, count=len(items), items=items)
