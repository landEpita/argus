import { describe, expect, it } from "vitest";
import { createLayerRegistry } from "./registry";
import type { FeatureLayer } from "./types";

function layer(id: string, overrides: Partial<FeatureLayer> = {}): FeatureLayer {
  return {
    id,
    label: id,
    group: "movement",
    refreshMs: 5_000,
    defaultEnabled: false,
    style: { color: "#fff", radius: 2 },
    load: async () => ({ type: "FeatureCollection", features: [] }),
    ...overrides,
  };
}

describe("createLayerRegistry", () => {
  it("looks layers up by id and lists defaults", () => {
    const registry = createLayerRegistry([layer("a", { defaultEnabled: true }), layer("b")]);
    expect(registry.get("b")?.id).toBe("b");
    expect(registry.get("missing")).toBeUndefined();
    expect(registry.defaults()).toEqual(new Set(["a"]));
    expect(registry.all()).toHaveLength(2);
  });

  it("groups layers preserving order", () => {
    const registry = createLayerRegistry([
      layer("a"),
      layer("quake", { group: "events" }),
      layer("b"),
    ]);
    expect(
      registry
        .byGroup()
        .get("movement")
        ?.map((l) => l.id),
    ).toEqual(["a", "b"]);
    expect(
      registry
        .byGroup()
        .get("events")
        ?.map((l) => l.id),
    ).toEqual(["quake"]);
  });

  it("rejects duplicate ids", () => {
    expect(() => createLayerRegistry([layer("a"), layer("a")])).toThrow("duplicate layer id: a");
  });

  it("rejects refresh rates that would hammer upstreams", () => {
    expect(() => createLayerRegistry([layer("a", { refreshMs: 10 })])).toThrow("refreshMs");
  });
});
