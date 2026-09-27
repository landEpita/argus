import { describe, expect, it } from "vitest";
import type { Convergence } from "@/lib/api/types";
import { corroborationLabel, toSituation } from "./situations";

const cell: Convergence = {
  id: "cell:1",
  cell: { west: 32, south: 48, east: 34, north: 50 },
  center: { lat: 49.2, lon: 33.1 },
  kinds: [
    { kind: "reported_violence", count: 3, examples: ["a"] },
    { kind: "air_alert", count: 1, examples: ["b"] },
    { kind: "military_aircraft", count: 2, examples: ["c"] },
  ],
  score: 4.5,
  latest: "2026-09-27T18:00:00Z",
  country: "UA",
};

describe("situations", () => {
  it("never counts press-coded reports as corroboration", () => {
    const s = toSituation(cell, 1, () => "Ukraine");
    expect(s.title).toBe("Air-raid alert with Military aircraft");
    expect(s.place).toBe("Ukraine · 49.2°, 33.1°");
    expect([s.corroborating, s.unverified]).toEqual([2, 1]);
    expect(s.signals.find((x) => x.kind === "reported_violence")?.unverified).toBe(true);
    expect(corroborationLabel(s)).toBe("2 independent kinds of signal agree");
  });

  it("says when only unverified signals remain", () => {
    const s = toSituation(
      { ...cell, country: null, kinds: [cell.kinds[0] as Convergence["kinds"][number]] },
      2,
      () => "",
    );
    expect(s.place).toBe("49.2°, 33.1°");
    expect(s.title).toBe("Reported violence");
    expect(corroborationLabel(s)).toBe("Unverified only — no corroboration");
    expect(corroborationLabel({ corroborating: 1, unverified: 0 })).toBe("Single kind of signal");
    expect(corroborationLabel({ corroborating: 1, unverified: 2 })).toContain("plus unverified");
  });
});
