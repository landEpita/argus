"""Query parameters shared by several routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query

from argus.domain.geo import BoundingBox


def bbox_param(
    bbox: Annotated[
        str | None, Query(description="west,south,east,north", examples=["2.0,48.5,2.8,49.1"])
    ] = None,
) -> BoundingBox | None:
    try:
        return BoundingBox.parse(bbox) if bbox else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid bbox: {exc}") from exc


BBoxParam = Annotated[BoundingBox | None, Depends(bbox_param)]
