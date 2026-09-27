/**
 * How layer features look on the Cesium globe: the same renderer-neutral
 * LayerStyle the MapLibre renderer reads, resolved per feature in plain code
 * (Cesium has no style expressions).
 */
import type { BBox } from "@/lib/geo";
import type { LayerStyle } from "../layers/types";

/** The colour MapLibre's colorExpression would give this feature. */
export function featureColor(
  style: LayerStyle,
  properties: Record<string, unknown>,
  watched: ReadonlySet<string>,
): string {
  if (style.highlight && watched.has(String(properties[style.highlight.property]))) {
    return style.highlight.color;
  }
  if (style.colorProperty) {
    const own = properties[style.colorProperty];
    if (typeof own === "string" && own) return own;
  }
  if (style.colorBy) {
    const value = style.colorBy.values[String(properties[style.colorBy.property])];
    if (value) return value;
  }
  return style.color;
}

/** Height above the ellipsoid, in metres, from what the feature reports; ground otherwise. */
export function featureHeight(properties: Record<string, unknown>): number {
  const m = properties.altitude_m;
  if (typeof m === "number" && Number.isFinite(m)) return Math.max(0, m);
  const km = properties.altitude_km;
  if (typeof km === "number" && Number.isFinite(km)) return Math.max(0, km * 1000);
  return 0;
}

/** Point size in pixels; objects are a little larger on the globe to stay visible. */
export function featureSize(style: LayerStyle, properties: Record<string, unknown>): number {
  if (!style.radiusBy) return style.radius * 2 + 2;
  const raw = Number(properties[style.radiusBy.property] ?? 0);
  const t = Number.isFinite(raw) ? Math.min(1, Math.max(0, raw)) : 0;
  return (style.radiusBy.min + t * (style.radiusBy.max - style.radiusBy.min)) * 2 + 2;
}

/**
 * The web-map zoom level that shows about as much as a camera at ``heightM``.
 * Layers use zoom for their minZoom rule; ~0 from 40 000 km, ~15 from 1 km.
 */
export function zoomForHeight(heightM: number): number {
  return Math.max(0, Math.min(22, Math.log2(40_000_000 / Math.max(heightM, 1))));
}

export function heightForZoom(zoom: number): number {
  return 40_000_000 / 2 ** zoom;
}

/** A view rectangle (radians) as a bbox, or the whole world when the sky is in view. */
export function rectangleToBBox(
  rect: { west: number; south: number; east: number; north: number } | undefined,
): BBox {
  if (!rect) return { west: -180, south: -85, east: 180, north: 85 };
  const deg = 180 / Math.PI;
  let west = rect.west * deg;
  let east = rect.east * deg;
  if (east < west) {
    // Crossing the antimeridian: the API takes west < east, so ask for the full width.
    west = -180;
    east = 180;
  }
  return {
    west,
    south: Math.max(-85, rect.south * deg),
    east,
    north: Math.min(85, rect.north * deg),
  };
}
