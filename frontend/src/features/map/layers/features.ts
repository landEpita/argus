import type { Feature, Point } from "geojson";
import type { LayerFeatures } from "./types";

type Properties = Record<string, unknown>;

export function pointFeature(
  id: string,
  lon: number,
  lat: number,
  properties: Properties,
): Feature<Point, Properties> {
  return { type: "Feature", id, geometry: { type: "Point", coordinates: [lon, lat] }, properties };
}

export function collection(features: Feature<Point, Properties>[]): LayerFeatures {
  return { type: "FeatureCollection", features };
}

/** The key a watched object is matched on, shared by the watch store and the map style. */
export const watchKey = (kind: string, value: string) => `${kind}:${value}`;

export const WATCH_HIGHLIGHT = { property: "watch_key", color: "#f43f5e" } as const;
