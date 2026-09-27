import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { ChokepointTraffic } from "@/lib/api/types";
import { chokepointLayer, chokepointsToFeatures, TRAFFIC_COLORS } from "./chokepoints";

const hormuz: ChokepointTraffic = {
  id: "chokepoint6",
  name: "Strait of Hormuz",
  position: { lat: 26.6, lon: 56.3 },
  latest_date: "2026-09-20",
  last_7d_avg: 4.3,
  prior_90d_avg: 15.3,
  last_year_avg: 116,
  change_vs_90d_pct: -71.9,
  change_vs_last_year_pct: -96.3,
  tanker_share_pct: 40,
  daily: [],
  source: "portwatch",
};

describe("chokepoint layer", () => {
  it("classifies traffic against last year and keeps both baselines", () => {
    const [f] = chokepointsToFeatures([hormuz]).features;
    expect(f?.geometry).toEqual({ type: "Point", coordinates: [56.3, 26.6] });
    expect(f?.properties).toMatchObject({
      title: "Strait of Hormuz",
      status: "halted",
      traffic: "Traffic near zero",
      vs_last_year: "-96.3 %",
      vs_prior_90_days: "-71.9 %",
      data_as_of: "2026-09-20",
    });
  });

  it("says so when there is no baseline", () => {
    const [f] = chokepointsToFeatures([
      { ...hormuz, change_vs_last_year_pct: null, change_vs_90d_pct: null, tanker_share_pct: null },
    ]).features;
    expect(f?.properties).toMatchObject({
      status: "unknown",
      vs_last_year: null,
      tanker_share: null,
    });
  });

  it("colours by status and loads through the API", async () => {
    expect(chokepointLayer.style.colorBy?.values).toBe(TRAFFIC_COLORS);
    const api = { chokepoints: vi.fn(async () => [hormuz]) } as unknown as ApiClient;
    const data = await chokepointLayer.load({
      api,
      bbox: { west: 0, south: 0, east: 1, north: 1 },
      zoom: 2,
      signal: new AbortController().signal,
    });
    expect(data.features).toHaveLength(1);
  });
});
