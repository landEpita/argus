import { describe, expect, it } from "vitest";
import { refreshed } from "./LiveMedia";

describe("refreshed", () => {
  it("adds a per-second cache buster", () => {
    expect(refreshed("https://x.test/a.jpg", 5_500)).toBe("https://x.test/a.jpg?t=5");
    expect(refreshed("https://x.test/a.jpg?id=1", 5_000)).toBe("https://x.test/a.jpg?id=1&t=5");
  });
});
