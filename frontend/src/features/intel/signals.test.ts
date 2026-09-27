import { describe, expect, it } from "vitest";
import { missingInputs } from "./signals";

describe("missingInputs", () => {
  it("names the inputs that did not answer", () => {
    expect(
      missingInputs([
        { name: "events:conflict", ok: true, error: null },
        { name: "events:fires", ok: false, error: "capability_disabled" },
        { name: "news", ok: false, error: "x" },
      ]),
    ).toBe("Computed without: fires, news");
    expect(missingInputs([{ name: "news", ok: true, error: null }])).toBeNull();
  });
});
