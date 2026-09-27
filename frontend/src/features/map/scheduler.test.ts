import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiClient, ApiError } from "@/lib/api/client";
import { createLayerRegistry } from "./layers/registry";
import type { FeatureLayer, LayerContext, LayerFeatures } from "./layers/types";
import { LayerScheduler, type LayerUpdate } from "./scheduler";

const EMPTY: LayerFeatures = { type: "FeatureCollection", features: [] };
const PARIS = { west: 2, south: 48, east: 3, north: 49 };
const LYON = { west: 4, south: 45, east: 5, north: 46 };
const api = {} as ApiClient;

function setup(load: (ctx: LayerContext) => Promise<LayerFeatures>, minZoom?: number) {
  const layer: FeatureLayer = {
    minZoom,
    id: "aircraft",
    label: "Aircraft",
    group: "movement",
    refreshMs: 10_000,
    defaultEnabled: true,
    style: { color: "#fff", radius: 2 },
    load: vi.fn(load),
  };
  const updates: LayerUpdate[] = [];
  const timers = {
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>),
    now: () => 42,
  };
  const scheduler = new LayerScheduler(
    createLayerRegistry([layer]),
    api,
    (u) => updates.push(u),
    timers,
  );
  return { scheduler, layer, updates };
}

const statuses = (updates: LayerUpdate[]) => updates.map((u) => u.status);

describe("LayerScheduler", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("waits for a viewport before loading", async () => {
    const { scheduler, layer } = setup(async () => EMPTY);
    scheduler.enable("aircraft");
    await vi.runOnlyPendingTimersAsync();
    expect(layer.load).not.toHaveBeenCalled();

    scheduler.setViewport(PARIS);
    await vi.advanceTimersByTimeAsync(0);
    expect(layer.load).toHaveBeenCalledOnce();
  });

  it("publishes loading then ready", async () => {
    const { scheduler, updates } = setup(async () => EMPTY);
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(0);
    expect(updates).toEqual([
      { layerId: "aircraft", status: "loading" },
      { layerId: "aircraft", status: "ready", data: EMPTY, loadedAt: 42 },
    ]);
  });

  it("refreshes on the layer cadence without overlapping", async () => {
    const { scheduler, layer } = setup(async () => EMPTY);
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(9_999);
    expect(layer.load).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(layer.load).toHaveBeenCalledTimes(2);
  });

  it("keeps refreshing after an error", async () => {
    let calls = 0;
    const { scheduler, updates } = setup(async () => {
      calls += 1;
      if (calls === 1) throw new Error("503");
      return EMPTY;
    });
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(statuses(updates)).toEqual(["loading", "error", "loading", "ready"]);
  });

  it("aborts the in-flight request when the viewport moves", async () => {
    const seen: LayerContext[] = [];
    const { scheduler, updates } = setup(
      (ctx) =>
        new Promise((resolve) => {
          seen.push(ctx);
          setTimeout(() => resolve(EMPTY), 1_000);
        }),
    );
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    scheduler.setViewport(LYON);
    await vi.advanceTimersByTimeAsync(1_000);

    expect(seen.map((c) => c.bbox)).toEqual([PARIS, LYON]);
    expect(seen[0]?.signal.aborted).toBe(true);
    expect(statuses(updates)).toEqual(["loading", "loading", "ready"]);
  });

  it("stops everything on disable", async () => {
    const { scheduler, layer, updates } = setup(async () => EMPTY);
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(0);
    scheduler.disable("aircraft");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(layer.load).toHaveBeenCalledOnce();
    expect(updates.at(-1)).toEqual({ layerId: "aircraft", status: "disabled" });
    expect(scheduler.isEnabled("aircraft")).toBe(false);
  });

  it("ignores repeated enable and unknown disable", async () => {
    const { scheduler, layer } = setup(async () => EMPTY);
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    scheduler.enable("aircraft");
    scheduler.disable("nope");
    await vi.advanceTimersByTimeAsync(0);
    expect(layer.load).toHaveBeenCalledOnce();
  });

  it("marks disabled capabilities unavailable and stops polling them", async () => {
    const { scheduler, layer, updates } = setup(async () => {
      throw new ApiError(503, { error: "capability_disabled", capability: "events.fires" });
    });
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(statuses(updates)).toEqual(["loading", "unavailable"]);
    expect(layer.load).toHaveBeenCalledOnce();
  });

  it("keeps retrying other 503s", async () => {
    const { scheduler, layer } = setup(async () => {
      throw new ApiError(503, { error: "upstream_unavailable" });
    });
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    await vi.advanceTimersByTimeAsync(20_000);
    expect(layer.load).toHaveBeenCalledTimes(3);
  });

  it("does not load below the layer's minimum zoom, and resumes when zoomed in", async () => {
    const { scheduler, layer, updates } = setup(async () => EMPTY, 5);
    scheduler.enable("aircraft");
    scheduler.setViewport(PARIS, 3);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(layer.load).not.toHaveBeenCalled();
    expect(updates.at(-1)).toEqual({ layerId: "aircraft", status: "zoom" });

    scheduler.setViewport(PARIS, 6);
    await vi.advanceTimersByTimeAsync(0);
    expect(layer.load).toHaveBeenCalledOnce();
    expect(vi.mocked(layer.load).mock.calls[0]?.[0].zoom).toBe(6);
  });

  it("rejects unknown layers", () => {
    const { scheduler } = setup(async () => EMPTY);
    expect(() => scheduler.enable("ghost")).toThrow("unknown layer: ghost");
  });

  it("does nothing after dispose", async () => {
    const { scheduler, layer } = setup(async () => EMPTY);
    scheduler.setViewport(PARIS);
    scheduler.enable("aircraft");
    scheduler.dispose();
    scheduler.setViewport(LYON);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(layer.load).toHaveBeenCalledOnce();
  });
});
