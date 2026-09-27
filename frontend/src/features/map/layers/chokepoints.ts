import { TRAFFIC_LABELS, type TrafficStatus, trafficStatus } from "@/features/markets/format";
import type { ChokepointTraffic } from "@/lib/api/types";
import { collection, pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export const TRAFFIC_COLORS: Record<TrafficStatus, string> = {
  halted: "#dc2626",
  severe: "#f97316",
  reduced: "#facc15",
  normal: "#22c55e",
  busier: "#38bdf8",
  unknown: "#94a3b8",
};

export function chokepointsToFeatures(items: readonly ChokepointTraffic[]): LayerFeatures {
  return collection(
    items.map((c) => {
      const status = trafficStatus(c);
      return pointFeature(c.id, c.position.lon, c.position.lat, {
        title: c.name,
        status,
        traffic: TRAFFIC_LABELS[status],
        ships_per_day: c.last_7d_avg,
        vs_last_year: c.change_vs_last_year_pct === null ? null : `${c.change_vs_last_year_pct} %`,
        vs_prior_90_days: c.change_vs_90d_pct === null ? null : `${c.change_vs_90d_pct} %`,
        tanker_share: c.tanker_share_pct === null ? null : `${c.tanker_share_pct} %`,
        data_as_of: c.latest_date,
        source: "IMF PortWatch",
      });
    }),
  );
}

export const chokepointLayer: FeatureLayer = {
  id: "chokepoints",
  label: "Chokepoint traffic",
  group: "infrastructure",
  refreshMs: 3_600_000,
  defaultEnabled: false,
  note: "Ships per day vs the same week last year (IMF PortWatch, a few days behind)",
  style: {
    color: TRAFFIC_COLORS.unknown,
    radius: 8,
    colorBy: { property: "status", values: TRAFFIC_COLORS },
  },
  async load({ api, signal }) {
    return chokepointsToFeatures(await api.chokepoints(signal));
  },
};
