"""The MCP endpoint, spoken to as a client would: JSON-RPC over streamable HTTP."""

from typing import Any

import httpx

from argus.container import build_container
from argus.main import create_app
from tests.conftest import offline_settings, reset_schema
from tests.fakes import StubHttp

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(method: str, params: dict[str, Any] | None = None, id_: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


async def test_tools_are_listed_and_called_over_mcp() -> None:
    settings = offline_settings()
    container = build_container(settings, http=StubHttp())
    await reset_schema(container.db)
    app = create_app(settings, container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
            init = await c.post(
                "/mcp",
                headers=HEADERS,
                json=rpc("initialize", {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                }),
            )  # fmt: skip
            assert init.status_code == 200, init.text
            assert init.json()["result"]["serverInfo"]["name"] == "Argus"

            listed = (await c.post("/mcp", headers=HEADERS, json=rpc("tools/list", id_=2))).json()
            names = {t["name"] for t in listed["result"]["tools"]}
            assert {"news", "search", "country", "quotes", "chokepoints", "events"} <= names
            events = next(t for t in listed["result"]["tools"] if t["name"] == "events")
            assert set(events["inputSchema"]["required"]) == {"feed", "lat", "lon"}

            called = await c.post(
                "/mcp", headers=HEADERS,
                json=rpc(
                    "tools/call", {"name": "country", "arguments": {"iso2": "Ukraine"}}, id_=3
                ),
            )  # fmt: skip
            content = called.json()["result"]["content"][0]["text"]
            assert "iso2 must be a 2-letter country code" in content

            foreign = await c.post(
                "/mcp", headers={**HEADERS, "Host": "evil.example"}, json=rpc("tools/list", id_=4)
            )
            assert foreign.status_code in (400, 403, 421)
    await container.aclose()
