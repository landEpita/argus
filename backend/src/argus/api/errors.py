"""Map domain/provider exceptions to HTTP responses, in one place."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from argus.domain.errors import ConflictError, LimitExceededError, NotFoundError
from argus.providers.errors import AllProvidersFailedError, NoProviderError
from argus.services.infrastructure import TooManyTilesError


def _error(status: int, error: str, **detail: object) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, **detail})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AllProvidersFailedError)
    async def _all_failed(_: Request, exc: AllProvidersFailedError) -> JSONResponse:
        if exc.not_found:
            return _error(404, "not_found", capability=exc.capability)
        if exc.unsupported:
            return _error(
                422,
                "unsupported_query",
                capability=exc.capability,
                message="; ".join(str(e) for e in exc.errors),
            )
        return _error(
            503,
            "upstream_unavailable",
            capability=exc.capability,
            providers=[e.provider for e in exc.errors],
        )

    @app.exception_handler(NoProviderError)
    async def _no_provider(_: Request, exc: NoProviderError) -> JSONResponse:
        return _error(503, "capability_disabled", capability=exc.capability)

    @app.exception_handler(TooManyTilesError)
    async def _too_many_tiles(_: Request, exc: TooManyTilesError) -> JSONResponse:
        return _error(422, "zoom_in", message=str(exc))

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _error(404, "not_found", message=str(exc))

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return _error(409, "conflict", message=str(exc))

    @app.exception_handler(LimitExceededError)
    async def _limit(_: Request, exc: LimitExceededError) -> JSONResponse:
        return _error(422, "limit_exceeded", message=str(exc))
