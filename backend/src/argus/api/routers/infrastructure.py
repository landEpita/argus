from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from argus.api.deps import InfrastructureServiceDep
from argus.api.params import BBoxParam
from argus.domain.infrastructure import CableNetwork, Facility, FacilityKind

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])


class FacilityCollection(BaseModel):
    kind: FacilityKind
    count: int
    items: list[Facility]


@router.get("/facilities/{kind}", response_model=FacilityCollection)
async def list_facilities(
    kind: FacilityKind, service: InfrastructureServiceDep, bbox: BBoxParam
) -> FacilityCollection:
    """OpenStreetMap facilities in a box (at most 25 sq deg: zoom in for more)."""
    if bbox is None:
        raise HTTPException(status_code=422, detail="bbox is required")
    items = await service.facilities(kind, bbox)
    return FacilityCollection(kind=kind, count=len(items), items=items)


@router.get("/submarine-cables", response_model=CableNetwork)
async def submarine_cables(service: InfrastructureServiceDep) -> CableNetwork:
    """All submarine cables and landing points (TeleGeography, CC BY-NC-SA)."""
    return await service.cables()
