import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import { makeAircraft } from "@/test/fixtures";
import { aircraftLayer, aircraftToFeatures, militaryLayer, trackToFeatures } from "./aircraft";

describe("aircraftToFeatures", () => {
  it("builds lon/lat point features keyed by icao24", () => {
    const [feature] = aircraftToFeatures([makeAircraft()]).features;
    expect(feature?.id).toBe("abc123");
    expect(feature?.geometry).toEqual({ type: "Point", coordinates: [2.35, 48.85] });
    expect(feature?.properties.title).toBe("AFR1234");
  });

  it("falls back to the ICAO address and a zero heading", () => {
    const [feature] = aircraftToFeatures([
      makeAircraft({ callsign: null, heading_deg: null }),
    ]).features;
    expect(feature?.properties.title).toBe("ABC123");
    expect(feature?.properties.heading_deg).toBe(0);
  });
});

describe("aircraftLayer.load", () => {
  it("asks the API for the viewport", async () => {
    const aircraft = vi.fn(async () => ({ count: 1, items: [makeAircraft()] }));
    const api = { aircraft, health: vi.fn() } as unknown as ApiClient;
    const bbox = { west: 2, south: 48, east: 3, north: 49 };
    const signal = new AbortController().signal;

    const result = await aircraftLayer.load({ api, bbox, zoom: 6, signal });

    expect(aircraft).toHaveBeenCalledWith({ bbox }, signal);
    expect(result.features).toHaveLength(1);
  });
});

describe("trackToFeatures", () => {
  const point = (lat: number, lon: number, at: string) => ({
    at,
    position: { lat, lon },
    altitude_m: null,
    velocity_ms: null,
    heading_deg: null,
    on_ground: false,
  });

  it("draws a line and marks the first position", () => {
    const track = {
      icao24: "abc123",
      callsign: "AFR1",
      source: "adsblol",
      points: [point(48, 2, "2026-09-27T10:00:00Z"), point(49, 3, "2026-09-27T11:00:00Z")],
    };
    const { features } = trackToFeatures(track);
    expect(features[0]?.geometry).toEqual({
      type: "LineString",
      coordinates: [
        [2, 48],
        [3, 49],
      ],
    });
    expect(features[1]?.properties.title).toBe("AFR1 — first seen");
  });

  it("draws nothing for fewer than two points", () => {
    const track = { icao24: "abc123", callsign: null, source: "x", points: [point(1, 1, "t")] };
    expect(trackToFeatures(track).features).toEqual([]);
  });
});

describe("militaryLayer.load", () => {
  it("asks the military endpoint and keeps features watchable", async () => {
    const military = vi.fn(async () => ({ count: 1, items: [makeAircraft()] }));
    const api = { military } as unknown as ApiClient;
    const bbox = { west: 2, south: 48, east: 3, north: 49 };
    const result = await militaryLayer.load({
      api,
      bbox,
      zoom: 6,
      signal: new AbortController().signal,
    });
    expect(military).toHaveBeenCalledOnce();
    expect(result.features[0]?.properties.watch_key).toBe("aircraft:abc123");
    expect(militaryLayer.watchable).toBe("aircraft");
  });
});
