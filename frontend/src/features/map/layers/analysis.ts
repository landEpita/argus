import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { Convergence, CountrySignal, SignalKind } from "@/lib/api/types";
import { collection, pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export const SIGNAL_KIND_LABELS: Record<SignalKind, string> = {
  reported_violence: "Reported violence",
  military_aircraft: "Military aircraft",
  air_alert: "Air-raid alert",
  disaster: "Disaster",
  fire: "Fire hotspot",
  military_vessel: "Military vessel",
};

/**
 * Light orange → dark red, one hue family (reads for common colour-vision
 * deficiencies). Opacity rises with the score too, so the many countries with a
 * few points of news attention stay in the background instead of tinting the map.
 */
export const SCORE_STOPS = [
  [0, "#fed7aa"],
  [30, "#fb923c"],
  [60, "#dc2626"],
  [100, "#7f1d1d"],
] as const;

export const SCORE_OPACITY = [
  [0, 0],
  [10, 0],
  [20, 0.25],
  [50, 0.5],
  [100, 0.75],
] as const;

type Outlines = FeatureCollection<Geometry, { iso2: string; name: string }>;
let outlines: Promise<Outlines> | null = null;

/** Country polygons ship with the app (Natural Earth, public domain); loaded once. */
export function loadOutlines(fetchImpl: typeof fetch = fetch): Promise<Outlines> {
  outlines ??= fetchImpl("/geo/countries-110m.json").then((r) => {
    if (!r.ok) throw new Error(`country outlines: HTTP ${r.status}`);
    return r.json() as Promise<Outlines>;
  });
  return outlines;
}

export function resetOutlinesForTests(): void {
  outlines = null;
}

export function joinSignals(shapes: Outlines, signals: readonly CountrySignal[]): LayerFeatures {
  const byCode = new Map(signals.map((s) => [s.iso2, s]));
  return {
    type: "FeatureCollection",
    features: shapes.features.map((f): Feature<Geometry, Record<string, unknown>> => {
      const signal = byCode.get(f.properties.iso2);
      const properties: Record<string, unknown> = {
        title: f.properties.name,
        iso2: f.properties.iso2,
        score: signal?.score ?? 0,
        baseline: signal
          ? signal.has_baseline
            ? "relative to usual level"
            : "no baseline yet"
          : null,
      };
      for (const c of signal?.components ?? []) {
        if (c.points > 0) properties[c.component] = `${c.points} / ${c.max_points} pts`;
      }
      return { type: "Feature", id: f.properties.iso2, geometry: f.geometry, properties };
    }),
  };
}

export const countryIndexLayer: FeatureLayer = {
  id: "country-index",
  label: "Country Signal Index",
  group: "analysis",
  refreshMs: 300_000,
  defaultEnabled: false,
  note: "Disruptive activity the feeds report now — not a measure of stability",
  style: {
    color: "#f97316",
    radius: 0,
    geometry: "polygon",
    fillScale: { property: "score", stops: SCORE_STOPS, opacity: SCORE_OPACITY },
  },
  async load({ api, signal }) {
    const [shapes, signals] = await Promise.all([loadOutlines(), api.countrySignals(signal)]);
    return joinSignals(shapes, signals.items);
  },
};

export function convergenceToFeatures(items: readonly Convergence[]): LayerFeatures {
  return collection(
    items.map((c) =>
      pointFeature(c.id, c.center.lon, c.center.lat, {
        title: `${c.kinds.length} kinds of signal converging`,
        kinds: c.kinds.length,
        signals: c.kinds.map((k) => `${SIGNAL_KIND_LABELS[k.kind]} ×${k.count}`).join(", "),
        country: c.country,
        latest: c.latest,
        caveat: "co-location is a reason to look, not a conclusion",
      }),
    ),
  );
}

export const convergenceLayer: FeatureLayer = {
  id: "convergence",
  label: "Converging signals",
  group: "analysis",
  refreshMs: 300_000,
  defaultEnabled: false,
  note: "Places where independent kinds of signal coincide (2° cells)",
  style: {
    color: "#c084fc",
    radius: 8,
    radiusBy: { property: "kinds", min: 6, max: 16 },
  },
  async load({ api, signal }) {
    return convergenceToFeatures((await api.convergence(signal)).items);
  },
};
