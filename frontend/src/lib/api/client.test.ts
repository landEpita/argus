import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createApiClient", () => {
  it("requests aircraft with bbox and ground flag", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ count: 0, items: [] }));
    const api = createApiClient("http://api.test", fetchImpl);

    await api.aircraft({ bbox: { west: 2, south: 48, east: 3, north: 49 }, includeOnGround: true });

    const [url] = fetchImpl.mock.calls[0] as unknown as [string];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe("/api/v1/aviation/aircraft");
    expect(parsed.searchParams.get("bbox")).toBe("2.0000,48.0000,3.0000,49.0000");
    expect(parsed.searchParams.get("include_on_ground")).toBe("true");
  });

  it("omits bbox for a world query and uses same-origin by default", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ count: 0, items: [] }));
    await createApiClient(undefined, fetchImpl).aircraft({});
    const [url] = fetchImpl.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/v1/aviation/aircraft?include_on_ground=false");
  });

  it("builds the finance and system URLs", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}));
    const api = createApiClient("", fetchImpl);
    await api.asset("BZ=F", "3mo");
    await api.liquidations(["BTC", "ETH"]);
    await api.energyStocks();
    await api.capabilities();
    const urls = fetchImpl.mock.calls.map((c) => (c as unknown as [string])[0]);
    expect(urls).toEqual([
      "/api/v1/markets/assets/BZ%3DF?range=3mo",
      "/api/v1/markets/liquidations?symbols=BTC%2CETH",
      "/api/v1/macro/energy-stocks",
      "/api/v1/system/capabilities",
    ]);
  });

  it("throws ApiError carrying status and body", async () => {
    const body = { error: "upstream_unavailable" };
    const api = createApiClient("", async () => jsonResponse(body, 503));
    await expect(api.health()).rejects.toMatchObject({ status: 503, body });
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
  });

  it("tolerates non-JSON error bodies", async () => {
    const api = createApiClient("", async () => new Response("<html>", { status: 502 }));
    await expect(api.health()).rejects.toMatchObject({ status: 502, body: null });
  });

  it("forwards the abort signal", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ status: "ok", version: "0", sources: [] }));
    const controller = new AbortController();
    await createApiClient("", fetchImpl).health(controller.signal);
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.signal).toBe(controller.signal);
  });

  it("sends JSON bodies with PUT and POST", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ preferences: {}, updated_at: null }));
    const api = createApiClient("", fetchImpl);
    const prefs = { schema_version: 1 as const, enabled_layers: [], viewport: null };

    await api.savePreferences(prefs);

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/preferences");
    expect(init.method).toBe("PUT");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual(prefs);
  });

  it("covers the watchlist endpoints and treats 204 as empty", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "DELETE" ? new Response(null, { status: 204 }) : jsonResponse([]),
    );
    const api = createApiClient("", fetchImpl);

    await api.watchlists();
    await api.createWatchlist({ name: "Gulf" });
    await api.replaceWatchlist("a/b", { name: "Gulf" });
    await expect(api.deleteWatchlist("id-1")).resolves.toBeUndefined();

    const calls = fetchImpl.mock.calls.map(([url, init]) => `${init?.method} ${url}`);
    expect(calls).toEqual([
      "GET /api/v1/watchlists",
      "POST /api/v1/watchlists",
      "PUT /api/v1/watchlists/a%2Fb",
      "DELETE /api/v1/watchlists/id-1",
    ]);
  });

  it("reads stored preferences", async () => {
    const stored = { preferences: { schema_version: 1 }, updated_at: null };
    const api = createApiClient("", async () => jsonResponse(stored));
    expect(await api.preferences()).toEqual(stored);
  });

  it("builds the OSINT endpoints' URLs", async () => {
    const fetchImpl = vi.fn(async (_url: string) => jsonResponse({ items: [] }));
    const api = createApiClient("", fetchImpl);
    const bbox = { west: 2, south: 48, east: 3, north: 49 };

    await api.military({});
    await api.vessels({ bbox });
    await api.vessels({});
    await api.satellites("gps-ops");
    await api.feeds();
    await api.events("earthquakes", { bbox, sinceHours: 6, limit: 50 });
    await api.events("conflict", {});

    const urls = fetchImpl.mock.calls.map(([url]) => url);
    expect(urls).toEqual([
      "/api/v1/aviation/military?include_on_ground=false",
      "/api/v1/maritime/vessels?bbox=2.0000%2C48.0000%2C3.0000%2C49.0000",
      "/api/v1/maritime/vessels",
      "/api/v1/space/satellites?group=gps-ops",
      "/api/v1/events",
      "/api/v1/events/earthquakes?bbox=2.0000%2C48.0000%2C3.0000%2C49.0000&since_hours=6&limit=50",
      "/api/v1/events/conflict",
    ]);
  });
});
