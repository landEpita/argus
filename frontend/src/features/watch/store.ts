import { watchKey } from "@/features/map/layers/features";
import type { ApiClient } from "@/lib/api/client";
import type { WatchItem, WatchKind, Watchlist } from "@/lib/api/types";

export const WATCHED_LIST_NAME = "Watched";

type Listener = (keys: ReadonlySet<string>) => void;

/**
 * The "Watched" watchlist, as the map sees it: a set of `kind:value` keys.
 *
 * The list is created on the first watch. Updates are optimistic — the map
 * recolours immediately — and rolled back if the server refuses.
 */
export class WatchStore {
  private list: Watchlist | null = null;
  private keys = new Set<string>();
  private readonly listeners = new Set<Listener>();
  private queue: Promise<void> = Promise.resolve();

  constructor(
    private readonly api: ApiClient,
    private readonly onError: (error: unknown) => void = () => {},
  ) {}

  async load(signal?: AbortSignal): Promise<void> {
    try {
      const lists = await this.api.watchlists(signal);
      this.list = lists.find((l) => l.name === WATCHED_LIST_NAME) ?? null;
      this.setKeys(this.list?.items ?? []);
    } catch (error) {
      this.onError(error);
    }
  }

  has(kind: WatchKind, value: string): boolean {
    return this.keys.has(watchKey(kind, value));
  }

  watched(): ReadonlySet<string> {
    return this.keys;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Watch or unwatch. Calls are serialised so rapid clicks cannot race. */
  toggle(kind: WatchKind, value: string, label: string | null = null): Promise<void> {
    const run = () => this.applyToggle(kind, value, label);
    this.queue = this.queue.then(run, run);
    return this.queue;
  }

  private async applyToggle(kind: WatchKind, value: string, label: string | null) {
    const previous = this.list?.items ?? [];
    const watching = previous.some((i) => i.kind === kind && i.value === value);
    const items: WatchItem[] = watching
      ? previous.filter((i) => !(i.kind === kind && i.value === value))
      : [...previous, { kind, value, label }];

    this.setKeys(items); // optimistic
    try {
      this.list = this.list
        ? await this.api.replaceWatchlist(this.list.id, { name: this.list.name, items })
        : await this.api.createWatchlist({ name: WATCHED_LIST_NAME, items });
      this.setKeys(this.list.items);
    } catch (error) {
      this.setKeys(previous);
      this.onError(error);
    }
  }

  private setKeys(items: readonly WatchItem[]) {
    this.keys = new Set(items.map((i) => watchKey(i.kind, i.value)));
    for (const listener of this.listeners) listener(this.keys);
  }
}
