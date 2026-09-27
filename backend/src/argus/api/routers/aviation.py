from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel

from argus.api.deps import AviationServiceDep
from argus.api.params import BBoxParam
from argus.domain.aviation import Aircraft, AircraftQuery, AircraftTrack

router = APIRouter(prefix="/aviation", tags=["aviation"])


class AircraftCollection(BaseModel):
    count: int
    items: list[Aircraft]


@router.get("/aircraft", response_model=AircraftCollection)
async def list_aircraft(
    service: AviationServiceDep, bbox: BBoxParam, include_on_ground: bool = False
) -> AircraftCollection:
    items = await service.aircraft(AircraftQuery(bbox=bbox, include_on_ground=include_on_ground))
    return AircraftCollection(count=len(items), items=items)


@router.get("/military", response_model=AircraftCollection)
async def list_military(
    service: AviationServiceDep, bbox: BBoxParam, include_on_ground: bool = False
) -> AircraftCollection:
    """Aircraft flagged military by the aggregator's database. Worldwide unless `bbox`."""
    items = await service.military(AircraftQuery(bbox=bbox, include_on_ground=include_on_ground))
    return AircraftCollection(count=len(items), items=items)


@router.get("/aircraft/{icao24}/track", response_model=AircraftTrack)
async def aircraft_track(
    service: AviationServiceDep,
    icao24: Annotated[str, Path(pattern=r"^[0-9a-fA-F]{6}$", description="ICAO 24-bit address")],
) -> AircraftTrack:
    """Today's positions for one aircraft, oldest first (at most 2,000 points)."""
    return await service.track(icao24)
