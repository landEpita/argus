import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { Convergence, CountrySignal } from "@/lib/api/types";
import { fillExpressions, styleLayerIds, toMapLibreLayers } from "../render";
import {
  convergenceLayer,
  convergenceToFeatures,
  countryIndexLayer,
  joinSignals,
  loadOutlines,
  resetOutlinesForTests,
} from "./analysis";

const shapes = {
  type: "FeatureCollection" as const,
  features: [
    {
      type: "Feature" as const,
      properties: { iso2: "UA", name: "Ukraine" },
      geometry: { type: "Point" as const, coordinates: [32, 49] },
    },
    {
      type: "Feature" as const,
      properties: { iso2: "FR", name: "France" },
      geometry: { type: "Point" as const, coordinates: [2, 46] },
    },
  ],
};

const ua: CountrySignal = {
  iso2: "UA",
  name: "Ukraine",
  score: 63.3,
  has_baseline: false,
  computed_at: "2026-09-27T18:00:00Z",
  components: [
    {
      component: "reported_violence",
      raw: 20,
      points: 33,
      max_points: 35,
      rule: "r",
      mode: "absolute",
      baseline_mean: null,
      evidence: [],
    },
    {
      component: "internet_outages",
      raw: 0,
      points: 0,
      max_points: 15,
      rule: "r",
      mode: "absolute",
      baseline_mean: null,
      evidence: [],
    },
  ],
};

afterEach(() => resetOutlinesForTests());

describe("country index", () => {
  it("joins scores onto outlines; quiet countries stay at 0", () => {
    const [ukraine, france] = joinSignals(shapes, [ua]).features;
    expect(ukraine?.properties).toMatchObject({
      title: "Ukraine",
      score: 63.3,
      reported_violence: "33 / 35 pts",
      baseline: "no baseline yet",
    });
    expect(ukraine?.properties).not.toHaveProperty("internet_outages");
    expect(france?.properties).toMatchObject({ score: 0, baseline: null });
  });

  it("loads outlines once and scores through the API", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(shapes)));
    await loadOutlines(fetchImpl as unknown as typeof fetch);
    await loadOutlines(fetchImpl as unknown as typeof fetch);
    expect(fetchImpl).toHaveBeenCalledOnce();
    const api = {
      countrySignals: vi.fn(async () => ({ count: 1, items: [ua], inputs: [], method: [] })),
    } as unknown as ApiClient;
    const data = await countryIndexLayer.load({
      api,
      bbox: { west: 0, south: 0, east: 1, north: 1 },
      zoom: 2,
      signal: new AbortController().signal,
    });
    expect(data.features).toHaveLength(2);
  });

  it("reports missing outlines", async () => {
    await expect(
      loadOutlines(vi.fn(async () => new Response("", { status: 404 })) as unknown as typeof fetch),
    ).rejects.toThrow("HTTP 404");
  });

  it("renders as a fill plus outline, transparent where there is no score", () => {
    expect(styleLayerIds(countryIndexLayer)).toEqual([
      "argus-lyr-country-index",
      "argus-lyr-country-index-outline",
    ]);
    const [fill, outline] = toMapLibreLayers(countryIndexLayer, true);
    expect(fill?.type).toBe("fill");
    expect(outline?.type).toBe("line");
    const value = ["coalesce", ["to-number", ["get", "score"], 0], 0];
    const { opacity } = fillExpressions(countryIndexLayer.style);
    // Low scores fade out entirely; high ones stand out.
    expect(opacity).toEqual([
      "interpolate",
      ["linear"],
      value,
      0,
      0,
      10,
      0,
      20,
      0.25,
      50,
      0.5,
      100,
      0.75,
    ]);
    const plain = {
      color: "#fff",
      radius: 0,
      fillScale: { property: "score", stops: [[0, "#000"]] as const },
    };
    expect(fillExpressions(plain).opacity).toEqual(["case", [">", value, 0], 0.55, 0]);
    expect(fillExpressions({ color: "#fff", radius: 0 })).toEqual({ color: "#fff", opacity: 0.4 });
  });
});

describe("convergence", () => {
  const cell: Convergence = {
    id: "cell:16:24",
    cell: { west: 32, south: 48, east: 34, north: 50 },
    center: { lat: 49, lon: 33 },
    kinds: [
      { kind: "reported_violence", count: 3, examples: ["a"] },
      { kind: "air_alert", count: 1, examples: ["b"] },
    ],
    score: 4.5,
    latest: "2026-09-27T18:00:00Z",
    country: "UA",
  };

  it("becomes a point sized by the number of kinds, with the caveat", () => {
    const [f] = convergenceToFeatures([cell]).features;
    expect(f?.geometry).toEqual({ type: "Point", coordinates: [33, 49] });
    expect(f?.properties).toMatchObject({
      kinds: 2,
      signals: "Reported violence ×3, Air-raid alert ×1",
      country: "UA",
    });
    expect(String(f?.properties.caveat)).toContain("not a conclusion");
  });

  it("loads through the API", async () => {
    const api = {
      convergence: vi.fn(async () => ({ count: 1, items: [cell], inputs: [] })),
    } as unknown as ApiClient;
    const data = await convergenceLayer.load({
      api,
      bbox: { west: 0, south: 0, east: 1, north: 1 },
      zoom: 2,
      signal: new AbortController().signal,
    });
    expect(data.features).toHaveLength(1);
  });
});
