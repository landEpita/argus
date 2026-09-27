import { describe, expect, it } from "vitest";
import {
  featureColor,
  featureHeight,
  featureSize,
  heightForZoom,
  rectangleToBBox,
  zoomForHeight,
} from "./style";

describe("globe styles", () => {
  const style = {
    color: "#38bdf8",
    radius: 3,
    colorBy: { property: "kind", values: { a: "#111111" } },
    highlight: { property: "watch_key", color: "#f43f5e" },
  };

  it("resolves colours like the map's expressions", () => {
    expect(featureColor(style, { kind: "a" }, new Set())).toBe("#111111");
    expect(featureColor(style, { kind: "z" }, new Set())).toBe("#38bdf8");
    expect(featureColor(style, { kind: "a", watch_key: "k" }, new Set(["k"]))).toBe("#f43f5e");
    expect(featureColor({ ...style, colorProperty: "c" }, { c: "#222222" }, new Set())).toBe(
      "#222222",
    );
  });

  it("puts objects at their reported height", () => {
    expect(featureHeight({ altitude_m: 10_668 })).toBe(10_668);
    expect(featureHeight({ altitude_km: 420 })).toBe(420_000);
    expect(featureHeight({ altitude_m: null })).toBe(0);
    expect(featureSize({ color: "", radius: 3 }, {})).toBe(8);
    expect(
      featureSize({ color: "", radius: 3, radiusBy: { property: "s", min: 2, max: 6 } }, { s: 1 }),
    ).toBe(14);
  });

  it("maps camera height to zoom and view rectangles to boxes", () => {
    expect(zoomForHeight(heightForZoom(7))).toBeCloseTo(7, 6);
    expect(zoomForHeight(1e9)).toBe(0);
    const r = Math.PI / 180;
    expect(rectangleToBBox({ west: 2 * r, south: 48 * r, east: 3 * r, north: 49 * r })).toEqual({
      west: expect.closeTo(2, 6),
      south: expect.closeTo(48, 6),
      east: expect.closeTo(3, 6),
      north: expect.closeTo(49, 6),
    });
    expect(rectangleToBBox({ west: 170 * r, south: 0, east: -170 * r, north: r }).west).toBe(-180);
    expect(rectangleToBBox(undefined)).toEqual({ west: -180, south: -85, east: 180, north: 85 });
  });
});
