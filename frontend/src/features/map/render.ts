import type {
  DataDrivenPropertyValueSpecification,
  ExpressionSpecification,
  LayerSpecification,
  RasterSourceSpecification,
} from "maplibre-gl";
import type { FeatureLayer, LayerStyle, RasterData, RasterMapLayer } from "./layers/types";

export const ARROW_ICON = "argus-arrow";

export const sourceId = (layerId: string) => `argus-src-${layerId}`;
export const styleLayerId = (layerId: string) => `argus-lyr-${layerId}`;
const pointsLayerId = (layerId: string) => `argus-lyr-${layerId}-points`;

/** Every MapLibre style layer a map layer produces (a "mixed" layer makes two). */
export function styleLayerIds(layer: { id: string; kind?: string; style?: LayerStyle }): string[] {
  if (layer.kind !== "raster" && layer.style?.geometry === "mixed") {
    return [styleLayerId(layer.id), pointsLayerId(layer.id)];
  }
  if (layer.kind !== "raster" && layer.style?.geometry === "polygon") {
    return [styleLayerId(layer.id), `${styleLayerId(layer.id)}-outline`];
  }
  return [styleLayerId(layer.id)];
}

/** Polygon fill colour; features with no value (or 0) stay transparent. */
export function fillExpressions(style: LayerStyle): {
  color: DataDrivenPropertyValueSpecification<string>;
  opacity: DataDrivenPropertyValueSpecification<number>;
} {
  const scale = style.fillScale;
  if (!scale) return { color: style.color, opacity: 0.4 };
  const value: ExpressionSpecification = ["coalesce", ["to-number", ["get", scale.property], 0], 0];
  return {
    color: ["interpolate", ["linear"], value, ...scale.stops.flat()] as ExpressionSpecification,
    opacity: scale.opacity
      ? (["interpolate", ["linear"], value, ...scale.opacity.flat()] as ExpressionSpecification)
      : (["case", [">", value, 0], 0.55, 0] as ExpressionSpecification),
  };
}

/** Base colour, then per-feature or category colour, then watched highlight (which wins). */
export function colorExpression(
  style: LayerStyle,
  watched: readonly string[] = [],
): DataDrivenPropertyValueSpecification<string> {
  let color: DataDrivenPropertyValueSpecification<string> = style.color;
  if (style.colorBy) {
    const pairs = Object.entries(style.colorBy.values).flat();
    color = [
      "match",
      ["to-string", ["get", style.colorBy.property]],
      ...pairs,
      style.color,
    ] as ExpressionSpecification;
  }
  if (style.colorProperty) {
    color = ["coalesce", ["get", style.colorProperty], color] as ExpressionSpecification;
  }
  if (style.highlight && watched.length > 0) {
    color = [
      "case",
      ["in", ["to-string", ["get", style.highlight.property]], ["literal", [...watched]]],
      style.highlight.color,
      color,
    ] as ExpressionSpecification;
  }
  return color;
}

export function radiusExpression(style: LayerStyle): DataDrivenPropertyValueSpecification<number> {
  if (!style.radiusBy) return style.radius;
  const { property, min, max } = style.radiusBy;
  return [
    "interpolate",
    ["linear"],
    ["coalesce", ["to-number", ["get", property], 0], 0],
    0,
    min,
    1,
    max,
  ] as ExpressionSpecification;
}

/** Which paint property carries the colour, per style layer, for watchlist updates. */
export function colorPaintProperty(layer: FeatureLayer): "icon-color" | "circle-color" {
  return layer.style.rotationProperty ? "icon-color" : "circle-color";
}

const POINTS_ONLY: ExpressionSpecification = ["==", ["geometry-type"], "Point"];
const LINES_ONLY: ExpressionSpecification = [
  "in",
  ["geometry-type"],
  ["literal", ["LineString", "MultiLineString"]],
];

function pointSpec(
  layer: FeatureLayer,
  id: string,
  layout: { visibility: "visible" | "none" },
  watched: readonly string[],
  filter?: ExpressionSpecification,
): LayerSpecification {
  const { style } = layer;
  const common = { id, source: sourceId(layer.id), ...(filter ? { filter } : {}) };
  if (style.rotationProperty) {
    return {
      ...common,
      type: "symbol",
      layout: {
        ...layout,
        "icon-image": ARROW_ICON,
        "icon-size": style.radius / 6,
        "icon-rotate": ["get", style.rotationProperty],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
      paint: { "icon-color": colorExpression(style, watched) },
    };
  }
  return {
    ...common,
    type: "circle",
    layout,
    paint: {
      "circle-color": colorExpression(style, watched),
      "circle-radius": radiusExpression(style),
      "circle-opacity": 0.85,
      "circle-stroke-color": "#0b1220",
      "circle-stroke-width": 1,
    },
  };
}

/** Translate a renderer-neutral feature layer into MapLibre style layers. */
export function toMapLibreLayers(
  layer: FeatureLayer,
  visible: boolean,
  watched: readonly string[] = [],
): LayerSpecification[] {
  const layout = { visibility: visible ? "visible" : "none" } as const;
  const geometry = layer.style.geometry ?? "point";
  if (geometry === "point") return [pointSpec(layer, styleLayerId(layer.id), layout, watched)];
  if (geometry === "polygon") {
    const fill = fillExpressions(layer.style);
    return [
      {
        id: styleLayerId(layer.id),
        source: sourceId(layer.id),
        type: "fill",
        layout,
        paint: { "fill-color": fill.color, "fill-opacity": fill.opacity },
      },
      {
        id: `${styleLayerId(layer.id)}-outline`,
        source: sourceId(layer.id),
        type: "line",
        layout,
        paint: { "line-color": "#475569", "line-width": 0.5, "line-opacity": 0.6 },
      },
    ];
  }

  const line: LayerSpecification = {
    id: styleLayerId(layer.id),
    source: sourceId(layer.id),
    type: "line",
    filter: LINES_ONLY,
    layout: { ...layout, "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": colorExpression(layer.style, watched),
      "line-width": 1.2,
      "line-opacity": 0.8,
    },
  };
  if (geometry === "line") return [line];
  return [line, pointSpec(layer, pointsLayerId(layer.id), layout, watched, POINTS_ONLY)];
}

export function rasterSource(data: RasterData): RasterSourceSpecification {
  return {
    type: "raster",
    tiles: data.tiles,
    tileSize: data.tileSize,
    minzoom: data.minZoom,
    maxzoom: data.maxZoom,
    attribution: data.attribution,
  };
}

export function rasterLayerSpec(
  layer: RasterMapLayer,
  visible: boolean,
  opacity: number,
): LayerSpecification {
  return {
    id: styleLayerId(layer.id),
    source: sourceId(layer.id),
    type: "raster",
    layout: { visibility: visible ? "visible" : "none" },
    paint: { "raster-opacity": opacity, "raster-fade-duration": 0 },
  };
}

/** A north-pointing arrow as an SDF-compatible bitmap, so `icon-color` can tint it. */
export function arrowImage(size = 24): { width: number; height: number; data: Uint8Array } {
  const data = new Uint8Array(size * size * 4);
  const mid = (size - 1) / 2;
  for (let y = 0; y < size; y++) {
    // Half-width grows linearly from the tip (top) to the base (bottom).
    const halfWidth = (y / (size - 1)) * mid * 0.8;
    for (let x = 0; x < size; x++) {
      const inside = Math.abs(x - mid) <= halfWidth && y < size * 0.9;
      if (inside) data.set([255, 255, 255, 255], (y * size + x) * 4);
    }
  }
  return { width: size, height: size, data };
}
