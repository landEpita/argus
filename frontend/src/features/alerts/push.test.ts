import { describe, expect, it } from "vitest";
import { keyToBytes, pushSupported, subscriptionConfig } from "./push";

describe("web push helpers", () => {
  it("decodes base64url keys", () => {
    expect([...keyToBytes("AQID_-8")]).toEqual([1, 2, 3, 255, 239]);
  });

  it("keeps only what the server needs from a subscription", () => {
    expect(
      subscriptionConfig({ endpoint: "https://push.example/1", keys: { p256dh: "p", auth: "a" } }),
    ).toEqual({ endpoint: "https://push.example/1", p256dh: "p", auth: "a" });
    expect(() => subscriptionConfig({ endpoint: "https://x" })).toThrow("incomplete");
  });

  it("detects support", () => {
    expect(pushSupported(undefined)).toBe(false);
  });
});
