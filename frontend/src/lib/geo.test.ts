import { describe, expect, it } from "vitest";
import { bboxToParam, clampBBox, roundPosition } from "./geo";

describe("bboxToParam", () => {
  it("serialises west,south,east,north", () => {
    expect(bboxToParam({ west: 2, south: 48.5, east: 2.8, north: 49.1 })).toBe(
      "2.0000,48.5000,2.8000,49.1000",
    );
  });
});

describe("clampBBox", () => {
  it("clamps wrapped longitudes and polar latitudes", () => {
    expect(clampBBox({ west: -200, south: -95, east: 190, north: 91 })).toEqual({
      west: -180,
      south: -90,
      east: 180,
      north: 90,
    });
  });
});

describe("roundPosition", () => {
  it("rounds to storage precision", () => {
    expect(roundPosition(48.856614, 2.3522219, 6.123456)).toEqual({
      center: { lat: 48.8566, lon: 2.3522 },
      zoom: 6.12,
    });
  });
});
