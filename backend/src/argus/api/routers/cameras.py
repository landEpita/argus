from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from argus.api.deps import CameraServiceDep
from argus.api.params import BBoxParam
from argus.domain.cameras import NETWORKS, Camera, CameraNetwork, NetworkInfo

router = APIRouter(prefix="/cameras", tags=["cameras"])


class CameraCollection(BaseModel):
    count: int
    items: list[Camera]
    networks: list[CameraNetwork]
    unavailable: list[CameraNetwork]


@router.get("", response_model=CameraCollection)
async def list_cameras(
    service: CameraServiceDep,
    bbox: BBoxParam,
    network: Annotated[list[CameraNetwork] | None, Query()] = None,
) -> CameraCollection:
    """Open road cameras in a box, from the networks whose area it overlaps."""
    view = await service.cameras(bbox, set(network) if network else None)
    return CameraCollection(
        count=len(view.items), items=view.items,
        networks=view.networks, unavailable=view.unavailable,
    )  # fmt: skip


@router.get("/networks", response_model=list[NetworkInfo])
async def list_networks() -> list[NetworkInfo]:
    """The camera networks Argus reads, their area and licence."""
    return list(NETWORKS.values())
