"""
Argus as an MCP server (Model Context Protocol, streamable HTTP at ``/mcp``).

Claude Desktop, Claude Code or any MCP client can read Argus' data with the
same tools the built-in assistant uses — the client's own model does the
talking. Read-only, and bound to localhost like the rest of the API:

    claude mcp add --transport http argus http://localhost:8000/mcp
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import BaseRoute

from argus import __version__
from argus.api.deps import get_owner
from argus.services.assistant.tools import ToolContext, ToolError, ToolSet

INSTRUCTIONS = """Read-only access to Argus, an OSINT and markets console: news clustered
across outlets, Telegram OSINT channels, a per-country signal index, converging signals,
geolocated events (earthquakes, disasters, press-coded violence), military aircraft,
delayed market prices, chokepoint traffic. Every result names its sources. Press-coded
events (GDELT, "conflict") and Telegram posts are unverified: say so when you use them."""

# Hosts a local client uses; anything else is refused (DNS-rebinding protection).
LOCAL_HOSTS = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]:*", "argus.test"]


def build_mcp(tools: ToolSet) -> MCPServer:
    server = MCPServer("Argus", instructions=INSTRUCTIONS, version=__version__)

    async def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = tools.tools[name]
        try:
            out = await tool.run(
                {k: v for k, v in args.items() if v is not None}, ToolContext(get_owner())
            )
        except ToolError as exc:
            return {"error": str(exc)}
        return {"data": out.data, "sources": list(out.sources)}

    # Explicit signatures, so MCP clients get precise argument schemas.
    async def news(
        query: str | None = None, country: str | None = None, hours: int = 24
    ) -> dict[str, Any]:
        """News stories clustered across outlets, newest first. `country` is ISO 3166-1 alpha-2."""
        return await call("news", {"query": query, "country": country, "hours": hours})

    async def search(query: str, hours: int = 72) -> dict[str, Any]:
        """Search recent news stories and the user's Telegram channels by words and meaning."""
        return await call("search", {"query": query, "hours": hours})

    async def country(iso2: str) -> dict[str, Any]:
        """A country's signal index (0-100: disruptive activity reported now, not stability)."""
        return await call("country", {"iso2": iso2})

    async def situations() -> dict[str, Any]:
        """Places where several independent kinds of signal converge right now."""
        return await call("situations", {})

    async def events(
        feed: str, lat: float, lon: float, radius_km: float = 300, hours: int = 24
    ) -> dict[str, Any]:
        """Events near a point. feed: earthquakes, disaster-alerts, conflict (press-coded,
        unverified), air-alerts, internet-outages or natural-events."""
        return await call(
            "events", {"feed": feed, "lat": lat, "lon": lon, "radius_km": radius_km, "hours": hours}
        )

    async def military_aircraft(lat: float, lon: float, radius_km: float = 300) -> dict[str, Any]:
        """Aircraft flagged as military near a point, right now (not exhaustive)."""
        return await call("military_aircraft", {"lat": lat, "lon": lon, "radius_km": radius_km})

    async def quotes() -> dict[str, Any]:
        """Delayed prices of the watch set: indices, oil, gas, metals, FX, rates."""
        return await call("quotes", {})

    async def asset(symbol: str) -> dict[str, Any]:
        """Technical reading of one instrument (Yahoo symbol, e.g. BZ=F): averages, RSI,
        52-week range, support and resistance. Descriptive, not a forecast."""
        return await call("asset", {"symbol": symbol})

    async def chokepoints() -> dict[str, Any]:
        """Ship traffic through strategic straits vs the same week last year (IMF PortWatch)."""
        return await call("chokepoints", {})

    for fn in (
        news,
        search,
        country,
        situations,
        events,
        military_aircraft,
        quotes,
        asset,
        chokepoints,
    ):
        if fn.__name__ in tools.tools:
            server.add_tool(fn, name=fn.__name__)
    return server


def mcp_routes(server: MCPServer) -> list[BaseRoute]:
    """The streamable-HTTP route, to add to the FastAPI app (stateless JSON: no sessions)."""
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=LOCAL_HOSTS,
            allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
        ),
    )
    return list(app.routes)
