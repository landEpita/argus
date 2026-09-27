from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from argus.api.deps import MaritimeServiceDep
from argus.api.params import BBoxParam
from argus.domain.maritime import Vessel, VesselQuery

router = APIRouter(prefix="/maritime", tags=["maritime"])


class VesselCollection(BaseModel):
    count: int
    truncated: bool
    items: list[Vessel]


@router.get("/vessels", response_model=VesselCollection)
async def list_vessels(
    service: MaritimeServiceDep,
    bbox: BBoxParam,
    limit: Annotated[int, Query(ge=1, le=20_000)] = 5_000,
) -> VesselCollection:
    """Latest position of vessels heard recently (needs an AISStream key)."""
    page = await service.vessels(VesselQuery(bbox=bbox), limit)
    return VesselCollection(count=len(page.items), truncated=page.truncated, items=page.items)
