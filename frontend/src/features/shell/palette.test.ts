import { describe, expect, it } from "vitest";
import { type Command, filterCommands } from "./palette";

const cmd = (label: string, kind = "Layer"): Command => ({ id: label, label, kind, run() {} });

describe("command palette", () => {
  const all = [cmd("Show Earthquakes"), cmd("Go to Markets", "Space"), cmd("Earth imagery")];

  it("keeps the given order without a query, up to the limit", () => {
    expect(filterCommands(all, "", 2).map((c) => c.label)).toEqual([
      "Show Earthquakes",
      "Go to Markets",
    ]);
  });

  it("needs every word and ranks prefix matches first", () => {
    expect(filterCommands(all, "earth").map((c) => c.label)).toEqual([
      "Earth imagery",
      "Show Earthquakes",
    ]);
    expect(filterCommands(all, "markets space").map((c) => c.label)).toEqual(["Go to Markets"]);
    expect(filterCommands(all, "nothing")).toEqual([]);
  });
});
