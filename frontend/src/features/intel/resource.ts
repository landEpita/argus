export interface ResourceState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** When `data` was last refreshed successfully (ms epoch). */
  updatedAt: number | null;
}

interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  now(): number;
}

const realTimers: Timers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};

/**
 * A periodically refreshed value, independent of React.
 *
 * On failure the last good data is kept (with its age) and the error is set
 * alongside it: a flaky feed shows slightly old news, not an empty panel.
 * Changing the loader's inputs (a filter, the channel list) calls `refresh`.
 */
export class PollingResource<T> {
  private state: ResourceState<T> = { data: null, error: null, loading: false, updatedAt: null };
  private readonly listeners = new Set<(state: ResourceState<T>) => void>();
  private controller: AbortController | null = null;
  private timer: unknown = null;
  private started = false;

  constructor(
    private load: (signal: AbortSignal) => Promise<T>,
    private readonly intervalMs: number,
    private readonly timers: Timers = realTimers,
  ) {}

  get snapshot(): ResourceState<T> {
    return this.state;
  }

  subscribe(listener: (state: ResourceState<T>) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    void this.refresh();
  }

  stop(): void {
    this.started = false;
    this.controller?.abort();
    this.timers.clearTimeout(this.timer);
    this.timer = null;
  }

  /** Swap the loader (new filters) and fetch now. */
  setLoader(load: (signal: AbortSignal) => Promise<T>): void {
    this.load = load;
    if (this.started) void this.refresh();
  }

  async refresh(): Promise<void> {
    this.controller?.abort();
    this.timers.clearTimeout(this.timer);
    const controller = new AbortController();
    this.controller = controller;
    this.set({ loading: true });
    try {
      const data = await this.load(controller.signal);
      if (controller.signal.aborted) return;
      this.set({ data, error: null, loading: false, updatedAt: this.timers.now() });
    } catch (error) {
      if (controller.signal.aborted) return;
      this.set({ error, loading: false });
    }
    if (this.started)
      this.timer = this.timers.setTimeout(() => void this.refresh(), this.intervalMs);
  }

  private set(patch: Partial<ResourceState<T>>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener(this.state);
  }
}
