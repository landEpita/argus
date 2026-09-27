import type { EventCategory, EventFeed, GeoEvent } from "@/lib/api/types";
import { collection, pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export const EVENT_COLORS: Readonly<Partial<Record<EventCategory, string>>> = {
  earthquake: "#f97316",
  tsunami: "#0ea5e9",
  volcano: "#dc2626",
  wildfire: "#f43f5e",
  fire_hotspot: "#fb7185",
  tropical_cyclone: "#8b5cf6",
  severe_storm: "#a78bfa",
  flood: "#3b82f6",
  drought: "#ca8a04",
  landslide: "#a16207",
  sea_ice: "#e0f2fe",
  dust_haze: "#d6d3d1",
  extreme_temperature: "#fb923c",
  armed_conflict: "#ef4444",
  air_raid_alert: "#facc15",
  launch: "#e879f9",
  internet_outage: "#94a3b8",
};

export function eventsToFeatures(events: readonly GeoEvent[]): LayerFeatures {
  return collection(
    events.map((e) =>
      pointFeature(e.id, e.position.lon, e.position.lat, {
        title: e.title,
        category: e.category,
        severity: e.severity,
        magnitude: e.magnitude === null ? null : `${e.magnitude} ${e.magnitude_unit ?? ""}`.trim(),
        occurred_at: e.occurred_at,
        url: e.url,
        source: e.source,
        ...e.details,
      }),
    ),
  );
}

interface EventLayerOptions {
  id: string;
  label: string;
  sinceHours: number;
  refreshMs: number;
  defaultEnabled?: boolean;
  note?: string;
  radius?: [min: number, max: number];
}

export function eventLayer(feed: EventFeed, options: EventLayerOptions): FeatureLayer {
  const [min, max] = options.radius ?? [3, 12];
  return {
    id: options.id,
    label: options.label,
    group: "events",
    refreshMs: options.refreshMs,
    defaultEnabled: options.defaultEnabled ?? false,
    note: options.note,
    style: {
      color: "#94a3b8",
      radius: min,
      colorBy: { property: "category", values: EVENT_COLORS as Record<string, string> },
      radiusBy: { property: "severity", min, max },
    },
    async load({ api, bbox, signal }) {
      const { items } = await api.events(feed, { bbox, sinceHours: options.sinceHours }, signal);
      return eventsToFeatures(items);
    },
  };
}

export const eventLayers: readonly FeatureLayer[] = [
  eventLayer("earthquakes", {
    id: "earthquakes",
    label: "Earthquakes (24 h)",
    sinceHours: 24,
    refreshMs: 60_000,
    defaultEnabled: true,
  }),
  eventLayer("disaster-alerts", {
    id: "disaster-alerts",
    label: "Disaster alerts (7 d)",
    sinceHours: 24 * 7,
    refreshMs: 900_000,
    radius: [5, 14],
  }),
  eventLayer("natural-events", {
    id: "natural-events",
    label: "Natural events (30 d)",
    sinceHours: 24 * 30,
    refreshMs: 900_000,
  }),
  eventLayer("air-alerts", {
    id: "air-alerts",
    label: "Air-raid alerts (Ukraine)",
    sinceHours: 1,
    refreshMs: 30_000,
    radius: [9, 9],
    note: "Community mirror; drawn at each oblast's main city, not at a target",
  }),
  eventLayer("launches", {
    id: "launches",
    label: "Launches (next ones)",
    sinceHours: 24,
    refreshMs: 3_600_000,
    radius: [6, 6],
    note: "Launch Library 2 — pads of upcoming and last-day launches",
  }),
  eventLayer("internet-outages", {
    id: "internet-outages",
    label: "Internet outages (48 h)",
    sinceHours: 48,
    refreshMs: 600_000,
    radius: [5, 12],
    note: "IODA signal drops at country level; the cause is not known",
  }),
  eventLayer("fires", {
    id: "fires",
    label: "Fire hotspots (24 h)",
    sinceHours: 24,
    refreshMs: 900_000,
    radius: [2, 6],
    note: "Needs a NASA FIRMS key on the server",
  }),
  eventLayer("conflict", {
    id: "conflict",
    label: "Reported violence (6 h)",
    sinceHours: 6,
    refreshMs: 300_000,
    // Small markers: hundreds of noisy reports should not dominate the map.
    radius: [2, 5],
    note: "Machine-coded from news (GDELT): leads, not facts",
  }),
];
