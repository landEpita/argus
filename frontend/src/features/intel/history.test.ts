import { describe, expect, it } from "vitest";
import type { CountrySignal } from "@/lib/api/types";
import { bucketHistory, describeSignal } from "./history";

const NOW = Date.parse("2026-09-27T18:00:00Z");

describe("country history", () => {
  it("averages snapshots into buckets and keeps gaps empty", () => {
    const bars = bucketHistory(
      [
        { at: "2026-09-27T17:00:00Z", score: 60 },
        { at: "2026-09-27T16:00:00Z", score: 70 },
        { at: "2026-09-20T19:00:00Z", score: 10 },
        { at: "2026-09-01T00:00:00Z", score: 99 },
      ],
      NOW,
    );
    expect(bars).toHaveLength(28);
    expect(bars.at(-1)?.score).toBe(65);
    expect(bars[0]?.score).toBe(10);
    expect(bars.filter((b) => b.score === null)).toHaveLength(26);
  });

  it("summarises from the figures and says what is weak", () => {
    const signal = {
      iso2: "UA",
      name: "Ukraine",
      score: 48,
      has_baseline: false,
      computed_at: "2026-09-27T18:00:00Z",
      components: [
        {
          component: "reported_violence",
          raw: 3,
          points: 33,
          max_points: 35,
          rule: "",
          mode: "absolute",
          baseline_mean: null,
          evidence: [],
        },
        {
          component: "air_alerts",
          raw: 4,
          points: 15,
          max_points: 15,
          rule: "",
          mode: "absolute",
          baseline_mean: null,
          evidence: [],
        },
        {
          component: "news_attention",
          raw: 0,
          points: 0,
          max_points: 25,
          rule: "",
          mode: "absolute",
          baseline_mean: null,
          evidence: [],
        },
      ],
    } as CountrySignal;
    const text = describeSignal("Ukraine", signal, "Computed without: news");
    expect(text).toContain(
      "48 / 100, from reported violence (33 of 35), air-raid alerts (15 of 15).",
    );
    expect(text).toContain("no baseline yet");
    expect(text).toContain("not a count of facts");
    expect(text).toContain("Computed without: news.");
    expect(describeSignal("France", null, null)).toBe(
      "No disruptive signal about France in the feeds right now.",
    );
  });
});
