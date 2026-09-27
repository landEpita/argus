import { describe, expect, it } from "vitest";
import { hashFor, parseHash } from "./space";

describe("space routing", () => {
  it("reads the space and its parameter from the hash", () => {
    expect(parseHash("")).toEqual({ space: "map", param: null });
    expect(parseHash("#markets")).toEqual({ space: "markets", param: null });
    expect(parseHash("#/countries/UA")).toEqual({ space: "countries", param: "UA" });
    expect(parseHash("#markets/BZ%3DF")).toEqual({ space: "markets", param: "BZ=F" });
    expect(parseHash("#nowhere")).toEqual({ space: "map", param: null });
  });

  it("writes hashes that read back", () => {
    expect(hashFor("map")).toBe("");
    expect(hashFor("markets", "^GSPC")).toBe("#markets/%5EGSPC");
    expect(parseHash(hashFor("markets", "^GSPC"))).toEqual({ space: "markets", param: "^GSPC" });
  });
});
