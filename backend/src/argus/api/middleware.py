"""
Request middleware: request id, access log, HTTP metrics.

Pure ASGI rather than ``BaseHTTPMiddleware``, which buffers responses and
breaks context-variable propagation.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from argus.infra.logging import request_id_var
from argus.infra.metrics import Metrics

logger = logging.getLogger("argus.access")

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER.encode():
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None


def route_template(scope: Scope) -> str:
    """
    ``/api/v1/watchlists/{watchlist_id}`` for ``/api/v1/watchlists/3f2a…``.

    Rebuilt from the matched path parameters rather than read from framework
    internals (FastAPI's ``scope["route"]`` omits parent router prefixes).
    Requests that matched no endpoint collapse into one ``unmatched`` series,
    so scanners probing random URLs cannot blow up metric cardinality.
    """
    if scope.get("endpoint") is None:
        return "unmatched"
    names_by_value = {str(v): k for k, v in scope.get("path_params", {}).items()}
    return "/".join(
        f"{{{names_by_value[segment]}}}" if segment in names_by_value else segment
        for segment in scope["path"].split("/")
    )


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, metrics: Metrics | None = None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            route = route_template(scope)
            method = scope["method"]
            if self.metrics is not None:
                self.metrics.http_requests.labels(method, route, str(status)).inc()
                self.metrics.http_latency.labels(method, route).observe(elapsed)
            logger.info(
                "%s %s %s",
                method,
                scope["path"],
                status,
                extra={"route": route, "status": status, "duration_ms": round(elapsed * 1000, 1)},
            )
            request_id_var.reset(token)
