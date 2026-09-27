import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { Watchlist, WatchlistDraft } from "@/lib/api/types";
import { WATCHED_LIST_NAME, WatchStore } from "./store";

function list(items: Watchlist["items"], name = WATCHED_LIST_NAME): Watchlist {
  return { id: "w1", name, items, created_at: "t", updated_at: "t" };
}

function fakeApi(existing: Watchlist[]) {
  const createWatchlist = vi.fn(async (draft: WatchlistDraft) =>
    list(
      (draft.items ?? []).map((i) => ({ kind: i.kind, value: i.value, label: i.label ?? null })),
    ),
  );
  const replaceWatchlist = vi.fn(async (_id: string, draft: WatchlistDraft) =>
    list(
      (draft.items ?? []).map((i) => ({ kind: i.kind, value: i.value, label: i.label ?? null })),
    ),
  );
  const watchlists = vi.fn(async () => existing);
  const api = { watchlists, createWatchlist, replaceWatchlist } as unknown as ApiClient;
  return { api, createWatchlist, replaceWatchlist };
}

describe("WatchStore", () => {
  it("loads the Watched list and ignores others", async () => {
    const { api } = fakeApi([
      list([{ kind: "vessel", value: "227006760", label: null }], "Other"),
      list([{ kind: "aircraft", value: "abc123", label: null }]),
    ]);
    const store = new WatchStore(api);
    await store.load();
    expect(store.has("aircraft", "abc123")).toBe(true);
    expect(store.has("vessel", "227006760")).toBe(false);
  });

  it("creates the list on first watch, then replaces it", async () => {
    const { api, createWatchlist, replaceWatchlist } = fakeApi([]);
    const store = new WatchStore(api);
    await store.load();

    await store.toggle("aircraft", "abc123", "AFR1");
    expect(createWatchlist).toHaveBeenCalledWith({
      name: WATCHED_LIST_NAME,
      items: [{ kind: "aircraft", value: "abc123", label: "AFR1" }],
    });

    await store.toggle("aircraft", "abc123");
    expect(replaceWatchlist).toHaveBeenCalledWith("w1", { name: WATCHED_LIST_NAME, items: [] });
    expect(store.has("aircraft", "abc123")).toBe(false);
  });

  it("notifies subscribers optimistically and rolls back on failure", async () => {
    const { api, createWatchlist } = fakeApi([]);
    createWatchlist.mockRejectedValueOnce(new Error("500"));
    const onError = vi.fn();
    const store = new WatchStore(api, onError);
    const seen: string[][] = [];
    store.subscribe((keys) => seen.push([...keys]));

    await store.toggle("vessel", "227006760");

    expect(seen).toEqual([["vessel:227006760"], []]);
    expect(onError).toHaveBeenCalledOnce();
  });

  it("serialises rapid toggles", async () => {
    const { api, createWatchlist, replaceWatchlist } = fakeApi([]);
    const store = new WatchStore(api);
    await Promise.all([store.toggle("aircraft", "aaaaaa"), store.toggle("aircraft", "bbbbbb")]);
    expect(createWatchlist).toHaveBeenCalledOnce();
    expect(replaceWatchlist).toHaveBeenCalledOnce();
    expect([...store.watched()].sort()).toEqual(["aircraft:aaaaaa", "aircraft:bbbbbb"]);
  });

  it("reports load failures without throwing", async () => {
    const api = {
      watchlists: vi.fn(async () => {
        throw new Error("down");
      }),
    } as unknown as ApiClient;
    const onError = vi.fn();
    await new WatchStore(api, onError).load();
    expect(onError).toHaveBeenCalledOnce();
  });

  it("unsubscribes", async () => {
    const { api } = fakeApi([]);
    const store = new WatchStore(api);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();
    await store.toggle("aircraft", "abc123");
    expect(listener).not.toHaveBeenCalled();
  });
});
