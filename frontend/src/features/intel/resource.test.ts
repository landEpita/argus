import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PollingResource } from "./resource";

const timers = {
  setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clearTimeout: (h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>),
  now: () => 1_000,
};

describe("PollingResource", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("loads on start and refreshes on its interval", async () => {
    let n = 0;
    const resource = new PollingResource(async () => ++n, 5_000, timers);
    resource.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(resource.snapshot).toEqual({ data: 1, error: null, loading: false, updatedAt: 1_000 });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(resource.snapshot.data).toBe(2);
    resource.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(resource.snapshot.data).toBe(2);
  });

  it("keeps the last good data when a refresh fails", async () => {
    let fail = false;
    const resource = new PollingResource(
      async () => {
        if (fail) throw new Error("503");
        return "news";
      },
      1_000,
      timers,
    );
    resource.start();
    await vi.advanceTimersByTimeAsync(0);
    fail = true;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(resource.snapshot.data).toBe("news");
    expect(resource.snapshot.error).toBeInstanceOf(Error);
    fail = false;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(resource.snapshot.error).toBeNull();
  });

  it("a new loader cancels the in-flight request and applies immediately", async () => {
    const seen: string[] = [];
    const resource = new PollingResource<string>(
      (signal) =>
        new Promise((resolve) => {
          seen.push("slow");
          signal.addEventListener("abort", () => resolve("aborted"));
        }),
      10_000,
      timers,
    );
    resource.start();
    resource.setLoader(async () => {
      seen.push("fast");
      return "filtered";
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(seen).toEqual(["slow", "fast"]);
    expect(resource.snapshot.data).toBe("filtered");
  });

  it("notifies subscribers and allows unsubscribing", async () => {
    const resource = new PollingResource(async () => 1, 1_000, timers);
    const listener = vi.fn();
    const off = resource.subscribe(listener);
    resource.start();
    resource.start(); // idempotent
    await vi.advanceTimersByTimeAsync(0);
    expect(listener).toHaveBeenCalledTimes(2); // loading, then data
    off();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(listener).toHaveBeenCalledTimes(2);
    resource.stop();
  });

  it("setLoader before start only stores the loader", async () => {
    const load = vi.fn(async () => 1);
    const resource = new PollingResource(async () => 0, 1_000, timers);
    resource.setLoader(load);
    await vi.advanceTimersByTimeAsync(0);
    expect(load).not.toHaveBeenCalled();
  });
});
