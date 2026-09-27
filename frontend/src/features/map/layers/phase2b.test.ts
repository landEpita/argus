import { describe, expect, it, vi } from "vitest";
import { errorReason, layerStatus } from "@/components/map/layerStatus";
import type { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/client";
import type { CableNetwork, RasterLayer } from "@/lib/api/types";
import { imageryLayers, RasterUnavailableError, toRasterData } from "./imagery";
import {
  cablesLayer,
  cablesToFeatures,
  facilitiesToFeatures,
  infrastructureLayers,
} from "./infrastructure";

const bbox = { west: 2, south: 48, east: 3, north: 49 };
const signal = new AbortController().signal;

const radar: RasterLayer = {
  id: "weather-radar",
  label: "Radar",
  tiles: ["https://r/{z}/{x}/{y}.png"],
  tile_size: 256,
  min_zoom: 0,
  max_zoom: 7,
  attribution: "© RainViewer",
  valid_at: "2026-09-27T16:20:00Z",
  opacity: 0.7,
};

describe("infrastructure", () => {
  it("facility layers need zoom 5 and ask for their kind", async () => {
    const facilities = vi.fn(async () => ({ kind: "military", count: 0, items: [] }));
    const api = { facilities } as unknown as ApiClient;
    const military = infrastructureLayers.find((l) => l.id === "facility-military");
    expect(military?.minZoom).toBe(5);
    await military?.load({ api, bbox, zoom: 6, signal });
    expect(facilities).toHaveBeenCalledWith("military", bbox, signal);
  });

  it("facilities become points with an OSM link", () => {
    const [f] = facilitiesToFeatures([
      {
        id: "osm:way/1",
        kind: "military",
        name: null,
        position: { lat: 1, lon: 2 },
        operator: null,
        subtype: "airfield",
        url: "https://osm.org/way/1",
        source: "overpass-de",
      },
    ]).features;
    expect(f?.properties).toMatchObject({
      title: "Unnamed site",
      subtype: "airfield",
      url: "https://osm.org/way/1",
    });
  });

  it("cables become multilines with their own colour, landing points become points", async () => {
    const network: CableNetwork = {
      cables: [
        {
          id: "c1",
          name: "2Africa",
          color: "#ff0000",
          lines: [
            [
              [0, 0],
              [1, 1],
            ],
          ],
        },
      ],
      landing_points: [{ id: "p1", name: "Marseille", position: { lat: 43.3, lon: 5.4 } }],
      source: "telegeography",
      attribution: "© TeleGeography",
    };
    const { features } = cablesToFeatures(network);
    expect(features[0]?.geometry).toEqual({
      type: "MultiLineString",
      coordinates: [
        [
          [0, 0],
          [1, 1],
        ],
      ],
    });
    expect(features[0]?.properties).toMatchObject({ title: "2Africa", color: "#ff0000" });
    expect(features[1]?.geometry.type).toBe("Point");
    const api = { cables: vi.fn(async () => network) } as unknown as ApiClient;
    expect((await cablesLayer.load({ api, bbox, zoom: 2, signal })).features).toHaveLength(2);
    expect(cablesLayer.style.geometry).toBe("mixed");
  });
});

describe("imagery", () => {
  it("maps the API raster to renderer data", () => {
    expect(toRasterData(radar)).toEqual({
      tiles: radar.tiles,
      tileSize: 256,
      minZoom: 0,
      maxZoom: 7,
      attribution: "© RainViewer",
      validAt: radar.valid_at,
      opacity: 0.7,
    });
  });

  it("each raster layer picks its entry, and says so when the server lacks it", async () => {
    const api = { rasters: vi.fn(async () => [radar]) } as unknown as ApiClient;
    const [radarLayer, trueColor] = imageryLayers;
    expect((await radarLayer?.load({ api, bbox, zoom: 3, signal }))?.maxZoom).toBe(7);
    await expect(trueColor?.load({ api, bbox, zoom: 3, signal })).rejects.toBeInstanceOf(
      RasterUnavailableError,
    );
  });
});

describe("layer status line", () => {
  const NOW = Date.parse("2026-09-27T18:00:00Z");
  it.each([
    [{ layerId: "x", status: "zoom" as const }, "Zoom in to load", ""],
    [
      { layerId: "x", status: "unavailable" as const },
      "○ Not configured on the server · key required",
      "",
    ],
    [
      {
        layerId: "x",
        status: "ready" as const,
        data: toRasterData(radar),
        loadedAt: NOW - 120_000,
      },
      "Updated 2 min ago · image of 16:20 UTC",
      "",
    ],
    [
      {
        layerId: "x",
        status: "ready" as const,
        data: { type: "FeatureCollection" as const, features: [] },
        loadedAt: NOW,
      },
      "Updated just now",
      "0",
    ],
    [{ layerId: "x", status: "loading" as const }, "Loading…", "…"],
  ])("%o", (update, text, count) => {
    expect(layerStatus(true, update, NOW)).toMatchObject({ text, count });
  });

  it("is off when disabled, and explains errors", () => {
    expect(layerStatus(false, undefined, NOW)).toEqual({ text: "Off", tone: "dim", count: "" });
    expect(
      layerStatus(true, { layerId: "x", status: "error", error: new Error("boom") }, NOW),
    ).toEqual({ text: "▲ boom", tone: "warn", count: "—" });
  });
});

describe("errorReason", () => {
  it.each([
    [
      new ApiError(503, { error: "upstream_unavailable", providers: ["opensky", "adsblol"] }),
      "No source answered (opensky, adsblol); retrying",
    ],
    [
      new ApiError(422, { error: "zoom_in", message: "view needs 20 tiles (max 16): zoom in" }),
      "view needs 20 tiles (max 16): zoom in",
    ],
    [new ApiError(500, null), "HTTP 500"],
    [new Error("boom"), "boom"],
    ["weird", "Unknown error"],
  ])("%o", (error, text) => {
    expect(errorReason({ layerId: "x", status: "error", error })).toBe(text);
  });

  it("is empty for non-errors", () => {
    expect(errorReason({ layerId: "x", status: "loading" })).toBeUndefined();
  });
});
