"use client";

import dynamic from "next/dynamic";

// MapLibre touches `window` on import, so the map is client-only.
export const MapShell = dynamic(() => import("@/features/map/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <div className="loading">Loading map…</div>,
});
