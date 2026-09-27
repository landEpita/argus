import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { CameraCollection } from "@/lib/api/types";
import { styleLayerIds, toMapLibreLayers } from "../render";
import {
  CONE_REACH_M,
  camerasLayer,
  camerasToFeatures,
  destination,
  facingLabel,
  viewCone,
} from "./cameras";

const page: CameraCollection = {
  count: 2,
  networks: ["drivebc", "fintraffic"],
  unavailable: ["fintraffic"],
  items: [
    {
      id: "drivebc:900",
      network: "drivebc",
      name: "Whiskers Point - S",
      position: { lat: 54.9, lon: -122.93 },
      heading_deg: 180,
      feed: "image",
      url: "https://www.drivebc.ca/images/900.jpg",
      still_url: "https://www.drivebc.ca/images/900.jpg",
      description: null,
      source: "drivebc",
    },
    {
      id: "tfl:1",
      network: "tfl",
      name: "A406",
      position: { lat: 51.5, lon: -0.1 },
      heading_deg: null,
      feed: "video",
      url: "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/1.mp4",
      still_url: null,
      description: "Home",
      source: "tfl",
    },
  ],
};

describe("open cameras", () => {
  it("draws a cone only where the operator states a facing", () => {
    const { features, meta, count } = camerasToFeatures(page);
    expect(count).toBe(2);
    expect(features.map((f) => f.geometry.type)).toEqual(["Polygon", "Point", "Point"]);
    expect(features[1]?.properties).toMatchObject({ facing: "S (180°)", feed: "image" });
    expect(features[2]?.properties).toMatchObject({ facing: "not stated by the operator" });
    expect(meta).toEqual({ note: "Not reachable: Fintraffic", warn: true });
  });

  it("points the cone along the heading", () => {
    const [lon, lat] = destination(0, 0, 90, CONE_REACH_M);
    expect(lat).toBeCloseTo(0, 6);
    expect(lon).toBeGreaterThan(0);
    const ring = viewCone(54.9, -122.93, 180).coordinates[0] ?? [];
    expect(ring[0]).toEqual(ring.at(-1));
    expect(ring.slice(1, -1).every(([, la]) => (la ?? 0) < 54.9)).toBe(true);
    expect(facingLabel(44)).toBe("NE (44°)");
  });

  it("renders fills under points and loads through the API", async () => {
    expect(styleLayerIds(camerasLayer)).toHaveLength(2);
    expect(toMapLibreLayers(camerasLayer, true).map((l) => l.type)).toEqual(["fill", "circle"]);
    const api = { cameras: vi.fn(async () => page) } as unknown as ApiClient;
    const bbox = { west: -1, south: 50, east: 1, north: 52 };
    const data = await camerasLayer.load({
      api,
      bbox,
      zoom: 8,
      signal: new AbortController().signal,
    });
    expect(data.features).toHaveLength(3);
  });
});
