import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { Preferences, StoredPreferences } from "@/lib/api/types";
import { PreferencesStore, resolveEnabledLayers } from "./store";

function fakeApi(stored: Preferences | Error) {
  const savePreferences = vi.fn(
    async (p: Preferences): Promise<StoredPreferences> => ({ preferences: p, updated_at: "now" }),
  );
  const preferences = vi.fn(async (): Promise<StoredPreferences> => {
    if (stored instanceof Error) throw stored;
    return { preferences: stored, updated_at: "then" };
  });
  const api = { preferences, savePreferences } as unknown as ApiClient;
  return { api, savePreferences };
}

const timers = {
  setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clearTimeout: (h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

const STORED: Preferences = {
  schema_version: 1,
  enabled_layers: ["aircraft"],
  viewport: { center: { lat: 1, lon: 2 }, zoom: 3 },
  projection: null,
  telegram_channels: null,
};

describe("PreferencesStore", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("loads stored preferences", async () => {
    const store = new PreferencesStore(fakeApi(STORED).api, 1_000, timers);
    expect(await store.load()).toEqual(STORED);
    expect(store.value).toEqual(STORED);
  });

  it("falls back to empty preferences when the API fails", async () => {
    const onError = vi.fn();
    const store = new PreferencesStore(fakeApi(new Error("down")).api, 1_000, timers, onError);
    expect(await store.load()).toEqual({
      schema_version: 1,
      enabled_layers: null,
      viewport: null,
      projection: null,
      telegram_channels: null,
    });
    expect(onError).toHaveBeenCalledOnce();
  });

  it("coalesces rapid updates into one save of the merged document", async () => {
    const { api, savePreferences } = fakeApi(STORED);
    const store = new PreferencesStore(api, 1_000, timers);
    await store.load();

    store.update({ viewport: { center: { lat: 5, lon: 5 }, zoom: 4 } });
    await vi.advanceTimersByTimeAsync(500);
    store.update({ enabled_layers: [] });
    await vi.advanceTimersByTimeAsync(999);
    expect(savePreferences).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(savePreferences).toHaveBeenCalledExactlyOnceWith({
      schema_version: 1,
      enabled_layers: [],
      viewport: { center: { lat: 5, lon: 5 }, zoom: 4 },
      projection: null,
      telegram_channels: null,
    });
  });

  it("flush saves a pending change immediately, and only once", async () => {
    const { api, savePreferences } = fakeApi(STORED);
    const store = new PreferencesStore(api, 1_000, timers);
    store.update({ enabled_layers: [] });
    await store.flush();
    await store.flush();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(savePreferences).toHaveBeenCalledOnce();
  });

  it("reports save failures and keeps working", async () => {
    const { api, savePreferences } = fakeApi(STORED);
    savePreferences.mockRejectedValueOnce(new Error("503"));
    const onError = vi.fn();
    const store = new PreferencesStore(api, 10, timers, onError);
    store.update({ enabled_layers: [] });
    await vi.advanceTimersByTimeAsync(10);
    expect(onError).toHaveBeenCalledOnce();
    store.update({ enabled_layers: ["aircraft"] });
    await vi.advanceTimersByTimeAsync(10);
    expect(savePreferences).toHaveBeenCalledTimes(2);
  });

  it("ignores updates after dispose", async () => {
    const { api, savePreferences } = fakeApi(STORED);
    const store = new PreferencesStore(api, 10, timers);
    store.update({ enabled_layers: [] });
    store.dispose();
    store.update({ enabled_layers: ["aircraft"] });
    await vi.advanceTimersByTimeAsync(100);
    expect(savePreferences).not.toHaveBeenCalled();
  });
});

describe("resolveEnabledLayers", () => {
  const known = new Set(["aircraft", "ships"]);
  const defaults = new Set(["aircraft"]);

  it("uses defaults when never chosen", () => {
    expect(resolveEnabledLayers(null, known, defaults)).toEqual(new Set(["aircraft"]));
  });

  it("respects an explicit empty choice", () => {
    expect(resolveEnabledLayers([], known, defaults)).toEqual(new Set());
  });

  it("drops layers this client does not know", () => {
    expect(resolveEnabledLayers(["ships", "removed-layer"], known, defaults)).toEqual(
      new Set(["ships"]),
    );
  });
});
