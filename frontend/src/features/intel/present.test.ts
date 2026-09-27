import { describe, expect, it } from "vitest";
import type { Story } from "@/lib/api/types";
import { coverageLabel, describeSource, parseChannel } from "./present";

describe("present", () => {
  it("describes a source's tier and ownership", () => {
    expect(describeSource({ id: "tass", name: "TASS", tier: 3, ownership: "state" })).toBe(
      "TASS — tier 3: State-controlled, no press freedom, state-controlled",
    );
  });

  it("labels coverage", () => {
    const story = (n: number) =>
      ({ sources: Array.from({ length: n }, (_, i) => ({ id: `s${i}` })) }) as unknown as Story;
    expect(coverageLabel(story(1))).toBe("1 source");
    expect(coverageLabel(story(4))).toBe("4 sources");
  });

  it.each([
    ["@OsintDefender", "osintdefender"],
    ["https://t.me/s/wartranslated/", "wartranslated"],
    ["t.me/Intel_Slava", "intel_slava"],
    ["no spaces", null],
    ["abc", null],
    ["", null],
  ])("parseChannel(%s)", (input, expected) => {
    expect(parseChannel(input)).toBe(expected);
  });
});
