import { describe, expect, it } from "vitest";
import { formatValue, popupRows } from "./format";

describe("formatValue", () => {
  it.each([
    ["altitude_m", 10_000, "10,000 m (32,808.4 ft)"],
    ["velocity_ms", 231.5, "231.5 m/s (450 kt)"],
    ["altitude_km", 426.1, "426.1 km"],
    ["severity", 0.534, "53 %"],
    ["tsunami_warning", true, "yes"],
    ["occurred_at", "2026-09-27T15:04:05Z", "2026-09-27 15:04 UTC"],
    ["place", "Tokyo", "Tokyo"],
  ])("%s", (key, value, expected) => {
    expect(formatValue(key, value)).toBe(expected);
  });

  it.each([null, undefined, ""])("hides empty values (%s)", (value) => {
    expect(formatValue("x", value)).toBeNull();
  });
});

describe("popupRows", () => {
  it("skips internal and empty properties and humanises labels", () => {
    const rows = popupRows({
      title: "AFR1",
      watch_key: "aircraft:abc123",
      heading_deg: 90,
      altitude_m: 1000,
      type_code: "A320",
      registration: null,
    });
    expect(rows).toEqual([
      { label: "Altitude", value: "1,000 m (3,280.8 ft)" },
      { label: "Type", value: "A320" },
    ]);
  });

  it("renders only http(s) urls as links", () => {
    expect(popupRows({ url: "https://usgs.gov/x" })).toEqual([
      { label: "Link", value: "open source", href: "https://usgs.gov/x" },
    ]);
    expect(popupRows({ url: "javascript:alert(1)" })).toEqual([]);
  });
});
