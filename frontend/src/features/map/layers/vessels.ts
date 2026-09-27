import type { ShipCategory, Vessel } from "@/lib/api/types";
import { collection, pointFeature, WATCH_HIGHLIGHT, watchKey } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export const SHIP_COLORS: Readonly<Record<ShipCategory, string>> = {
  cargo: "#22c55e",
  tanker: "#ef4444",
  passenger: "#3b82f6",
  fishing: "#eab308",
  military: "#a855f7",
  law_enforcement: "#6366f1",
  tug: "#14b8a6",
  high_speed: "#ec4899",
  pleasure: "#f472b6",
  other: "#94a3b8",
  unknown: "#64748b",
};

export function vesselsToFeatures(vessels: readonly Vessel[]): LayerFeatures {
  return collection(
    vessels.map((v) =>
      pointFeature(v.mmsi, v.position.lon, v.position.lat, {
        title: v.name ?? `MMSI ${v.mmsi}`,
        watch_kind: "vessel",
        watch_value: v.mmsi,
        watch_key: watchKey("vessel", v.mmsi),
        mmsi: v.mmsi,
        category: v.category,
        imo: v.imo,
        call_sign: v.call_sign,
        destination: v.destination,
        velocity_ms: v.speed_ms,
        heading_deg: v.heading_deg ?? v.course_deg ?? 0,
        last_seen: v.last_seen,
        source: v.source,
      }),
    ),
  );
}

export const vesselLayer: FeatureLayer = {
  id: "vessels",
  label: "Ships (AIS)",
  group: "movement",
  refreshMs: 30_000,
  defaultEnabled: false,
  watchable: "vessel",
  note: "Needs an AISStream key on the server",
  style: {
    color: SHIP_COLORS.unknown,
    radius: 3,
    rotationProperty: "heading_deg",
    colorBy: { property: "category", values: SHIP_COLORS },
    highlight: WATCH_HIGHLIGHT,
  },
  async load({ api, bbox, signal }) {
    const { items } = await api.vessels({ bbox }, signal);
    return vesselsToFeatures(items);
  },
};
