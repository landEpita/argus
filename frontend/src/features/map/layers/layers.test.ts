import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { GeoEvent, SatellitePosition, Vessel } from "@/lib/api/types";
import { layerRegistry } from ".";
import { eventLayers, eventsToFeatures } from "./events";
import { satelliteLayers, satellitesToFeatures } from "./satellites";
import { SHIP_COLORS, vesselLayer, vesselsToFeatures } from "./vessels";

const bbox = { west: 2, south: 48, east: 3, north: 49 };
const signal = new AbortController().signal;

const vessel: Vessel = {
  mmsi: "227006760",
  name: null,
  call_sign: null,
  imo: null,
  ship_type: 80,
  category: "tanker",
  position: { lat: 43.3, lon: 5.35 },
  speed_ms: 6,
  course_deg: 90,
  heading_deg: null,
  destination: "FOS",
  last_seen: "2026-09-27T16:00:00Z",
  source: "aisstream",
};

const quake: GeoEvent = {
  id: "usgs:1",
  category: "earthquake",
  title: "M 6.1",
  position: { lat: 35.7, lon: 139.7 },
  occurred_at: "2026-09-27T15:00:00Z",
  severity: 0.68,
  magnitude: 6.1,
  magnitude_unit: "mww",
  url: "https://usgs.gov/1",
  source: "usgs",
  details: { depth_km: 10 },
};

const iss: SatellitePosition = {
  norad_id: 25544,
  name: "ISS (ZARYA)",
  group: "stations",
  position: { lat: 1, lon: 2 },
  altitude_km: 420,
  speed_kms: 7.66,
  at: "2026-09-27T16:00:00Z",
  elements_age_days: 0.5,
};

describe("registry", () => {
  it("has unique ids and sensible defaults", () => {
    const ids = layerRegistry.all().map((l) => l.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(layerRegistry.defaults()).toEqual(new Set(["aircraft", "sat-stations", "earthquakes"]));
    expect([...layerRegistry.byGroup().keys()]).toEqual([
      "movement",
      "space",
      "events",
      "infrastructure",
      "analysis",
      "imagery",
    ]);
  });

  it("flags every key-dependent layer with a note", () => {
    for (const id of ["vessels", "fires"]) {
      expect(layerRegistry.get(id)?.note).toMatch(/key/);
    }
  });
});

describe("vessels", () => {
  it("builds watchable features, falling back on course and MMSI", () => {
    const [feature] = vesselsToFeatures([vessel]).features;
    expect(feature?.properties).toMatchObject({
      title: "MMSI 227006760",
      watch_key: "vessel:227006760",
      heading_deg: 90,
      category: "tanker",
    });
    expect(vesselLayer.style.colorBy?.values).toBe(SHIP_COLORS);
  });

  it("loads through the API", async () => {
    const vessels = vi.fn(async () => ({ count: 1, truncated: false, items: [vessel] }));
    const api = { vessels } as unknown as ApiClient;
    const result = await vesselLayer.load({ api, bbox, zoom: 6, signal });
    expect(vessels).toHaveBeenCalledWith({ bbox }, signal);
    expect(result.features).toHaveLength(1);
  });
});

describe("events", () => {
  it("flattens details and formats magnitude", () => {
    const [feature] = eventsToFeatures([quake]).features;
    expect(feature?.properties).toMatchObject({
      category: "earthquake",
      severity: 0.68,
      magnitude: "6.1 mww",
      depth_km: 10,
    });
    const [noMag] = eventsToFeatures([{ ...quake, magnitude: null }]).features;
    expect(noMag?.properties.magnitude).toBeNull();
  });

  it("each layer asks its own feed and window", async () => {
    const events = vi.fn(async () => ({
      feed: "conflict",
      count: 0,
      truncated: false,
      window_start: "t",
      items: [],
    }));
    const api = { events } as unknown as ApiClient;
    const conflict = eventLayers.find((l) => l.id === "conflict");
    await conflict?.load({ api, bbox, zoom: 6, signal });
    expect(events).toHaveBeenCalledWith("conflict", { bbox, sinceHours: 6 }, signal);
  });
});

describe("satellites", () => {
  it("one layer per group, each loading its group", async () => {
    const satellites = vi.fn(async () => ({ group: "starlink", count: 1, items: [iss] }));
    const api = { satellites } as unknown as ApiClient;
    const starlink = satelliteLayers.find((l) => l.id === "sat-starlink");
    const result = await starlink?.load({ api, bbox, zoom: 6, signal });
    expect(satellites).toHaveBeenCalledWith("starlink", signal);
    expect(result?.features[0]?.properties.title).toBe("ISS (ZARYA)");
    expect(satellitesToFeatures([iss]).features[0]?.id).toBe("25544");
  });
});
