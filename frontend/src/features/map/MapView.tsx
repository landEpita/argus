"use client";

import { useEffect, useMemo, useState } from "react";
import { Cockpit } from "@/components/Cockpit";
import { PreferencesStore } from "@/features/preferences/store";
import { WatchStore } from "@/features/watch/store";
import { createApiClient } from "@/lib/api/client";
import type { Preferences } from "@/lib/api/types";

/** Loads the user's preferences and watchlist, then opens the cockpit. */
export function MapView() {
  const api = useMemo(() => createApiClient(), []);
  const store = useMemo(() => new PreferencesStore(api), [api]);
  const watch = useMemo(() => new WatchStore(api), [api]);
  const [initial, setInitial] = useState<Preferences | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([store.load(controller.signal), watch.load(controller.signal)]).then(([prefs]) => {
      if (!controller.signal.aborted) setInitial(prefs);
    });
    const flush = () => void store.flush();
    window.addEventListener("pagehide", flush);
    return () => {
      controller.abort();
      window.removeEventListener("pagehide", flush);
      void store.flush();
    };
  }, [store, watch]);

  if (initial === null) return <div className="loading">Loading…</div>;
  return <Cockpit api={api} store={store} watch={watch} initial={initial} />;
}
