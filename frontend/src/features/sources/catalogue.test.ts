import { describe, expect, it } from "vitest";
import type { Health } from "@/lib/api/types";
import { familyOf, KEYS, keyConfigured, sourceRows, summarise } from "./catalogue";

const health: Health = {
  status: "failing",
  version: "t",
  sources: [
    {
      source: "usgs",
      status: "ok",
      last_success_age_s: 40,
      last_error: null,
      consecutive_failures: 0,
    },
    {
      source: "news:bbc",
      status: "ok",
      last_success_age_s: 90,
      last_error: null,
      consecutive_failures: 0,
    },
    {
      source: "news:tass",
      status: "failing",
      last_success_age_s: 900,
      last_error: "HTTP 503",
      consecutive_failures: 3,
    },
    {
      source: "polymarket",
      status: "failing",
      last_success_age_s: null,
      last_error: "DNS",
      consecutive_failures: 5,
    },
    {
      source: "eia",
      status: "idle",
      last_success_age_s: null,
      last_error: null,
      consecutive_failures: 0,
    },
    {
      source: "redis",
      status: "ok",
      last_success_age_s: 1,
      last_error: null,
      consecutive_failures: 0,
    },
  ],
};

describe("source catalogue", () => {
  it("groups outlets and mirrors into families", () => {
    expect(familyOf("news:bbc")).toBe("news");
    expect(familyOf("overpass-kumi")).toBe("overpass");
    expect(familyOf("usgs")).toBe("usgs");
  });

  it("puts the worst first and lists missing keys", () => {
    const rows = sourceRows(health, { "events.earthquakes": ["usgs"] });
    expect(rows.map((r) => [r.id, r.status])).toEqual([
      ["news", "down"],
      ["polymarket", "down"],
      ["aisstream", "needs-key"],
      ["firms", "needs-key"],
      ["eia", "idle"],
      ["usgs", "ok"],
    ]);
    const news = rows[0];
    expect(news).toMatchObject({ members: 2, lastError: "HTTP 503", lastSuccessAgeS: 90 });
    expect(summarise(rows)).toEqual({ ok: 1, down: 2, stale: 0, "needs-key": 2, idle: 1 });
  });

  it("knows whether a key is configured", () => {
    const ais = KEYS.find((k) => k.source === "aisstream");
    if (!ais) throw new Error("missing");
    expect(keyConfigured(ais, null)).toBeNull();
    expect(keyConfigured(ais, {})).toBe(false);
    expect(keyConfigured(ais, { "maritime.vessel_positions": ["aisstream"] })).toBe(true);
    expect(sourceRows(null, null)).toEqual([]);
  });
});
