from __future__ import annotations

from fastapi import APIRouter

from argus.api.deps import ImageryServiceDep
from argus.domain.imagery import RasterLayer

router = APIRouter(prefix="/imagery", tags=["imagery"])


@router.get("/rasters", response_model=list[RasterLayer])
async def list_rasters(service: ImageryServiceDep) -> list[RasterLayer]:
    """Tile overlays the map can show. The browser fetches tiles directly from the hosts."""
    return await service.layers()
