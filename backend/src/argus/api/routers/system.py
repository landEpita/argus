from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from argus import __version__
from argus.api.deps import ContainerDep, HealthDep, RegistryDep
from argus.infra.health import HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

READINESS_TIMEOUT_S = 3.0


class SourceHealthOut(BaseModel):
    source: str
    status: HealthStatus
    last_success_age_s: float | None
    last_error: str | None
    consecutive_failures: int


class HealthOut(BaseModel):
    status: HealthStatus
    version: str
    sources: list[SourceHealthOut]


class ReadinessOut(BaseModel):
    ready: bool
    checks: dict[str, str]


@router.get("/health", response_model=HealthOut)
def health(registry: HealthDep) -> HealthOut:
    """Passive view: what recent real traffic says about each upstream."""
    sources = [SourceHealthOut.model_validate(s, from_attributes=True) for s in registry.snapshot()]
    overall = (
        HealthStatus.FAILING
        if any(s.status is HealthStatus.FAILING for s in sources)
        else HealthStatus.OK
    )
    return HealthOut(status=overall, version=__version__, sources=sources)


@router.get("/ready", response_model=ReadinessOut, responses={503: {"model": ReadinessOut}})
async def ready(container: ContainerDep) -> JSONResponse:
    """Active probe of hard dependencies (database, cache). For orchestrators."""
    names = list(container.readiness)
    results = await asyncio.gather(
        *(asyncio.wait_for(container.readiness[name](), READINESS_TIMEOUT_S) for name in names),
        return_exceptions=True,
    )
    checks: dict[str, str] = {}
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("readiness check failed", extra={"check": name, "error": repr(result)})
            checks[name] = f"error: {type(result).__name__}"
        else:
            checks[name] = "ok"
    body = ReadinessOut(ready=all(v == "ok" for v in checks.values()), checks=checks)
    return JSONResponse(status_code=200 if body.ready else 503, content=body.model_dump())


@router.get("/capabilities")
def capabilities(registry: RegistryDep) -> dict[str, list[str]]:
    """Which provider serves each capability, in fallback order."""
    return registry.capabilities()


metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
def metrics(container: ContainerDep) -> Response:
    return Response(container.metrics.render(), media_type=container.metrics.content_type)


class MapConfigOut(BaseModel):
    cesium_ion_token: str | None = Field(
        description="Browser token for Cesium ion (terrain, 3D tiles); None = keyless globe"
    )


@router.get("/map-config", response_model=MapConfigOut)
async def map_config(container: ContainerDep) -> MapConfigOut:
    """What the 3D globe may load. The ion token is meant to be public (browser-side)."""
    return MapConfigOut(cesium_ion_token=container.settings.cesium_ion_token or None)
