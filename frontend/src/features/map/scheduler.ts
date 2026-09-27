import { type ApiClient, ApiError } from "@/lib/api/client";
import type { BBox } from "@/lib/geo";
import type { LayerRegistry } from "./layers/registry";
import type { LayerData } from "./layers/types";

export type LayerUpdate =
  | { layerId: string; status: "loading" }
  | { layerId: string; status: "ready"; data: LayerData; loadedAt: number }
  | { layerId: string; status: "error"; error: unknown }
  /** The backend has no provider for it (usually a missing API key). Not retried. */
  | { layerId: string; status: "unavailable" }
  /** The map is zoomed out beyond the layer's `minZoom`: nothing is requested. */
  | { layerId: string; status: "zoom" }
  | { layerId: string; status: "disabled" };

/** 503 capability_disabled: retrying cannot help until the server is reconfigured. */
export function isCapabilityDisabled(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 503) return false;
  const body = error.body as { error?: unknown } | null;
  return body?.error === "capability_disabled";
}

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  now(): number;
}

const realTimers: Timers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};

interface Running {
  controller: AbortController;
  timer: unknown;
}

/**
 * Drives every enabled layer: loads it for the current viewport, refreshes it
 * on its own cadence, and cancels stale requests when the viewport moves.
 * Framework-agnostic (Observer): the map component only subscribes to updates.
 *
 * Refreshes are chained with setTimeout rather than setInterval, so a slow
 * upstream never causes overlapping requests for the same layer.
 */
export class LayerScheduler {
  private readonly enabled = new Set<string>();
  private readonly running = new Map<string, Running>();
  private viewport: BBox | null = null;
  private zoom = 0;
  private disposed = false;

  constructor(
    private readonly registry: LayerRegistry,
    private readonly api: ApiClient,
    private readonly onUpdate: (update: LayerUpdate) => void,
    private readonly timers: Timers = realTimers,
  ) {}

  isEnabled(id: string): boolean {
    return this.enabled.has(id);
  }

  setViewport(bbox: BBox, zoom = this.zoom): void {
    this.viewport = bbox;
    this.zoom = zoom;
    for (const id of this.enabled) this.run(id);
  }

  enable(id: string): void {
    if (!this.registry.get(id)) throw new Error(`unknown layer: ${id}`);
    if (this.enabled.has(id)) return;
    this.enabled.add(id);
    this.run(id);
  }

  disable(id: string): void {
    if (!this.enabled.delete(id)) return;
    this.stop(id);
    this.onUpdate({ layerId: id, status: "disabled" });
  }

  dispose(): void {
    this.disposed = true;
    for (const id of [...this.running.keys()]) this.stop(id);
    this.enabled.clear();
  }

  private stop(id: string): void {
    const current = this.running.get(id);
    if (!current) return;
    current.controller.abort();
    this.timers.clearTimeout(current.timer);
    this.running.delete(id);
  }

  private run(id: string): void {
    const layer = this.registry.get(id);
    const bbox = this.viewport;
    if (!layer || !bbox || this.disposed) return;

    this.stop(id);
    if (layer.minZoom !== undefined && this.zoom < layer.minZoom) {
      this.onUpdate({ layerId: id, status: "zoom" });
      return; // re-evaluated on the next viewport change
    }
    const controller = new AbortController();
    const entry: Running = { controller, timer: undefined };
    this.running.set(id, entry);
    this.onUpdate({ layerId: id, status: "loading" });

    void this.load(id, bbox, controller, entry);
  }

  private async load(id: string, bbox: BBox, controller: AbortController, entry: Running) {
    const layer = this.registry.get(id);
    if (!layer) return;
    let data: LayerData;
    try {
      data = await layer.load({ api: this.api, bbox, zoom: this.zoom, signal: controller.signal });
    } catch (error) {
      if (controller.signal.aborted) return;
      if (isCapabilityDisabled(error)) {
        this.onUpdate({ layerId: id, status: "unavailable" });
        return; // no reschedule: it will not start working by itself
      }
      this.onUpdate({ layerId: id, status: "error", error });
      this.scheduleNext(id, layer.refreshMs, controller, entry);
      return;
    }
    if (controller.signal.aborted) return;
    this.onUpdate({ layerId: id, status: "ready", data, loadedAt: this.timers.now() });
    this.scheduleNext(id, layer.refreshMs, controller, entry);
  }

  private scheduleNext(id: string, ms: number, controller: AbortController, entry: Running) {
    if (controller.signal.aborted) return;
    entry.timer = this.timers.setTimeout(() => this.run(id), ms);
  }
}
