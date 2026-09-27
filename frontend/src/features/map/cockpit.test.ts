import { describe, expect, it } from "vitest";
import {
  angleDelta,
  bearingDeg,
  contacts,
  distanceKm,
  extrapolate,
  eyeHeight,
  type Fix,
  fixFrom,
  MAX_EXTRAPOLATION_S,
} from "./cockpit";

const T0 = 1_790_000_000_000;
const self: Fix = {
  id: "self",
  callsign: "AFR1",
  lat: 48,
  lon: 2,
  altitudeM: 10_000,
  speedMs: 250,
  headingDeg: 90,
  at: T0,
};

describe("cockpit geometry", () => {
  it("measures distance and bearing on the sphere", () => {
    expect(distanceKm(0, 0, 0, 1)).toBeCloseTo(111.19, 1);
    expect(bearingDeg(0, 0, 1, 0)).toBeCloseTo(0, 5);
    expect(bearingDeg(0, 0, 0, 1)).toBeCloseTo(90, 5);
    expect(angleDelta(350, 10)).toBe(20);
    expect(angleDelta(10, 350)).toBe(-20);
  });

  it("extrapolates along the reported track, and not forever", () => {
    const moved = extrapolate(self, T0 + 10_000);
    expect(moved.lat).toBeCloseTo(48, 3);
    expect(distanceKm(48, 2, moved.lat, moved.lon)).toBeCloseTo(2.5, 2);
    const capped = extrapolate(self, T0 + 3_600_000);
    expect(distanceKm(48, 2, capped.lat, capped.lon)).toBeCloseTo(
      (250 * MAX_EXTRAPOLATION_S) / 1000,
      1,
    );
    expect(extrapolate({ ...self, headingDeg: null }, T0 + 10_000)).toEqual({ lat: 48, lon: 2 });
  });

  it("lists nearby traffic, nearest first, relative to our nose", () => {
    const ahead: Fix = { ...self, id: "a", callsign: "AHEAD", lon: 2.5, altitudeM: 11_000 };
    const behind: Fix = { ...self, id: "b", callsign: "BEHIND", lon: 1.9, altitudeM: null };
    const far: Fix = { ...self, id: "c", lon: 12 };
    const list = contacts(self, [self, ahead, behind, far]);
    expect(list.map((c) => c.callsign)).toEqual(["BEHIND", "AHEAD"]);
    expect(list[1]?.relativeDeg).toBeCloseTo(0, 0);
    expect(list[1]?.altitudeDeltaM).toBe(1_000);
    expect(Math.abs(list[0]?.relativeDeg ?? 0)).toBeGreaterThan(170);
    expect(list[0]?.altitudeDeltaM).toBeNull();
  });

  it("reads fixes from aircraft features, keeping unknowns unknown", () => {
    const fix = fixFrom("abc", { title: "X", heading_deg: 0, heading_stated: false }, 1, 2, T0);
    expect(fix.headingDeg).toBeNull();
    expect(fix.altitudeM).toBeNull();
    expect(eyeHeight(fix)).toBe(30);
  });
});
