import { describe, expect, it } from "vitest";
import { place, restore } from "./wall";

describe("live wall", () => {
  it("places a channel in a tile, swapping if it is already shown", () => {
    expect(place(["a", "b", "c", "d"], 0, "e")).toEqual(["e", "b", "c", "d"]);
    expect(place(["a", "b", "c", "d"], 0, "c")).toEqual(["c", "b", "a", "d"]);
    expect(place(["a", "b"], 1, "b")).toEqual(["a", "b"]);
  });

  it("restores a saved wall against the catalog", () => {
    const catalog = ["a", "b", "c", "d", "e"];
    expect(restore(["e", "gone", "e", 3], catalog)).toEqual(["e", "a", "b", "c"]);
    expect(restore(null, catalog)).toEqual(["a", "b", "c", "d"]);
    expect(restore([], ["a"])).toEqual(["a"]);
  });
});
