import { describe, expect, it } from "vitest";
import { binEvents } from "./histogram";
import type { LayerFeatures } from "./layers/types";

const NOW = Date.parse("2026-09-27T18:00:00Z");

function events(...times: string[]): LayerFeatures {
  return {
    type: "FeatureCollection",
    features: times.map((t, i) => ({
      type: "Feature",
      id: i,
      properties: { occurred_at: t },
      geometry: { type: "Point", coordinates: [0, 0] },
    })),
  };
}

describe("event histogram", () => {
  it("stacks verified and press-coded events in 15-minute bins", () => {
    const bins = binEvents(
      new Map([
        ["earthquakes", events("2026-09-27T17:55:00Z", "2026-09-27T12:01:00Z", "bad")],
        ["conflict", events("2026-09-27T17:50:00Z", "2026-09-27T10:00:00Z")],
      ]),
      new Set(["conflict"]),
      NOW,
    );
    expect(bins).toHaveLength(24);
    expect(bins.at(-1)).toMatchObject({ verified: 1, unverified: 1 });
    expect(bins[0]).toMatchObject({ verified: 1, unverified: 0 });
    const total = bins.reduce((n, b) => n + b.verified + b.unverified, 0);
    expect(total).toBe(3); // outside the window and unparsable times are dropped
  });
});
