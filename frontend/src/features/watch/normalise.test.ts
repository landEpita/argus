import { describe, expect, it } from "vitest";
import { normaliseWatch } from "./normalise";

describe("watch input normalisation", () => {
  it.each([
    ["aircraft", " 3C6444 ", "3c6444"],
    ["vessel", "538009124", "538009124"],
    ["ticker", "bz=f", "BZ=F"],
    ["ticker", "^gspc", "^GSPC"],
    ["country", "tw", "TW"],
    ["keyword", "  strait   of hormuz ", "strait of hormuz"],
  ] as const)("%s %j → %s", (kind, raw, value) => {
    expect(normaliseWatch(kind, raw)).toEqual({ ok: true, value });
  });

  it.each([
    ["aircraft", "3C644"],
    ["vessel", "12345"],
    ["ticker", "BZ F"],
    ["country", "FRA"],
    ["keyword", "   "],
  ] as const)("rejects %s %j", (kind, raw) => {
    expect(normaliseWatch(kind, raw).ok).toBe(false);
  });
});
