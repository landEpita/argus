"""Application factory. ``uvicorn --factory argus.main:app`` or ``create_app()`` in tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from argus import __version__
from argus.api.errors import install_error_handlers
from argus.api.mcp import build_mcp, mcp_routes
from argus.api.middleware import RequestContextMiddleware
from argus.api.routers import (
    analysis,
    assistant,
    aviation,
    events,
    finance,
    imagery,
    infrastructure,
    intel,
    maritime,
    preferences,
    space,
    system,
    watchlists,
)
from argus.config import Settings
from argus.container import Container, build_container
from argus.infra.logging import configure_logging

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    # Building the container does no I/O (connections are lazy), so it can
    # happen here and the middleware can be wired to its metrics.
    container = container or build_container(settings)

    mcp = build_mcp(container.assistant.tools) if settings.mcp_enabled else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.start()
        try:
            if mcp is None:
                yield
            else:
                async with mcp.session_manager.run():
                    yield
        finally:
            await container.aclose()

    app = FastAPI(title="Argus API", version=__version__, lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    # Added last so it is outermost: it also times CORS and error handling.
    app.add_middleware(RequestContextMiddleware, metrics=container.metrics)
    # Cable routes and full event feeds are hundreds of KB of JSON: compress.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    install_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(system.router)
    api.include_router(aviation.router)
    api.include_router(maritime.router)
    api.include_router(space.router)
    api.include_router(events.router)
    api.include_router(infrastructure.router)
    api.include_router(imagery.router)
    api.include_router(intel.router)
    api.include_router(intel.countries_router)
    api.include_router(analysis.router)
    api.include_router(finance.router)
    api.include_router(watchlists.router)
    api.include_router(preferences.router)
    api.include_router(assistant.router)
    app.include_router(api)
    app.include_router(system.metrics_router)
    if mcp is not None:
        app.router.routes.extend(mcp_routes(mcp))
    return app


def app() -> FastAPI:
    """Factory for ``uvicorn --factory argus.main:app``."""
    return create_app()
