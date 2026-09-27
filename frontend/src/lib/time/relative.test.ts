import { describe, expect, it } from "vitest";
import { formatRelative, formatUtc } from "./relative";

const NOW = Date.parse("2026-09-27T12:00:00Z");
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

describe("formatRelative", () => {
  it.each([
    [10, "just now"],
    [-10, "in a moment"],
    [4 * 60, "4 min ago"],
    [59 * 60, "59 min ago"],
    [3 * 3600, "3 h ago"],
    [-2 * 3600, "in 2 h"],
    [3 * 86400, "3 d ago"],
  ])("%i s", (seconds, text) => {
    expect(formatRelative(ago(seconds), NOW)).toBe(text);
  });

  it("marks unknown times as unknown", () => {
    expect(formatRelative("not a date", NOW)).toBe("—");
    expect(formatUtc("nope")).toBe("—");
  });

  it("formats exact UTC", () => {
    expect(formatUtc("2026-09-27T15:04:59Z")).toBe("2026-09-27 15:04 UTC");
  });
});
