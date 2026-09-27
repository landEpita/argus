import { describe, expect, it } from "vitest";
import { sparklinePath } from "./sparkline";

describe("sparklinePath", () => {
  it("maps time to x and score to y, in time order", () => {
    const path = sparklinePath(
      [
        { at: "2026-09-27T12:00:00Z", score: 100 },
        { at: "2026-09-27T10:00:00Z", score: 0 },
        { at: "2026-09-27T11:00:00Z", score: 50 },
      ],
      100,
      20,
    );
    expect(path).toBe("M0.0,20.0 L50.0,10.0 L100.0,0.0");
  });

  it("clamps scores and handles one point or none", () => {
    expect(sparklinePath([{ at: "2026-09-27T10:00:00Z", score: 140 }], 80, 10)).toBe("M80.0,0.0");
    expect(sparklinePath([], 80, 10)).toBe("");
    expect(sparklinePath([{ at: "nope", score: 1 }], 80, 10)).toBe("");
  });
});
