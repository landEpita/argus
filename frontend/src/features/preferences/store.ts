import type { ApiClient } from "@/lib/api/client";
import type { Preferences } from "@/lib/api/types";

export interface DebounceTimers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

const realTimers: DebounceTimers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
};

const EMPTY: Preferences = {
  schema_version: 1,
  enabled_layers: null,
  viewport: null,
  projection: null,
  telegram_channels: null,
};

/**
 * Client-side owner of the user's preferences.
 *
 * Reads once at start-up, then coalesces rapid changes (panning fires many
 * `moveend`s) into one debounced PUT. Preferences are a convenience: if the
 * API is down the app still starts, with defaults, and saving is retried on
 * the next change.
 */
export class PreferencesStore {
  private current: Preferences = EMPTY;
  private timer: unknown = null;
  private disposed = false;

  constructor(
    private readonly api: ApiClient,
    private readonly debounceMs = 1_000,
    private readonly timers: DebounceTimers = realTimers,
    private readonly onError: (error: unknown) => void = () => {},
  ) {}

  get value(): Preferences {
    return this.current;
  }

  async load(signal?: AbortSignal): Promise<Preferences> {
    try {
      this.current = (await this.api.preferences(signal)).preferences;
    } catch (error) {
      this.onError(error);
      this.current = EMPTY;
    }
    return this.current;
  }

  update(patch: Partial<Omit<Preferences, "schema_version">>): void {
    if (this.disposed) return;
    this.current = { ...this.current, ...patch };
    this.timers.clearTimeout(this.timer);
    this.timer = this.timers.setTimeout(() => {
      this.timer = null;
      void this.save();
    }, this.debounceMs);
  }

  /** Save now if a change is pending (e.g. before the page unloads). */
  async flush(): Promise<void> {
    if (this.timer === null) return;
    this.timers.clearTimeout(this.timer);
    this.timer = null;
    await this.save();
  }

  dispose(): void {
    this.disposed = true;
    this.timers.clearTimeout(this.timer);
    this.timer = null;
  }

  private async save(): Promise<void> {
    try {
      await this.api.savePreferences(this.current);
    } catch (error) {
      this.onError(error);
    }
  }
}

/** Keep only layer ids the client knows, falling back to defaults if never chosen. */
export function resolveEnabledLayers(
  stored: readonly string[] | null | undefined,
  known: ReadonlySet<string>,
  defaults: ReadonlySet<string>,
): Set<string> {
  if (stored == null) return new Set(defaults);
  return new Set(stored.filter((id) => known.has(id)));
}
