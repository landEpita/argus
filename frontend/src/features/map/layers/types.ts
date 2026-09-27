import type { FeatureCollection, Geometry } from "geojson";
import type { ApiClient } from "@/lib/api/client";
import type { BBox } from "@/lib/geo";

export type LayerGroup =
  | "movement"
  | "space"
  | "events"
  | "infrastructure"
  | "analysis"
  | "imagery";

export interface LayerContext {
  bbox: BBox;
  zoom: number;
  api: ApiClient;
  signal: AbortSignal;
}

export type LayerFeatures = FeatureCollection<Geometry, Record<string, unknown>> & {
  /** How complete or fresh the data is, when the source says it is partial. */
  meta?: { note: string; warn?: boolean };
  /** Objects on screen, when features are not one per object (a camera and its cone). */
  count?: number;
};

/** How many objects a layer shows, formatted with a narrow space ("12\u202f345"). */
export function formatCount(data: LayerFeatures): string {
  return (data.count ?? data.features.length).toLocaleString("en").replaceAll(",", "\u202f");
}

/** Tile overlay description, renderer-neutral. */
export interface RasterData {
  tiles: string[];
  tileSize: number;
  minZoom: number;
  maxZoom: number;
  attribution: string;
  validAt: string | null;
  opacity: number;
}

export type LayerData = LayerFeatures | RasterData;

export const isRasterData = (data: LayerData): data is RasterData => "tiles" in data;

/**
 * How a feature layer is painted. Renderer-neutral on purpose: `render.ts` turns
 * it into MapLibre expressions; a Cesium renderer could read the same.
 */
export interface LayerStyle {
  color: string;
  radius: number;
  /**
   * "mixed" draws lines and points from one source (cables + landing points);
   * "polygon" fills areas (a choropleth) and is drawn beneath every other layer;
   * "cones" draws points with a translucent sector for where each one looks.
   */
  geometry?: "point" | "line" | "mixed" | "polygon" | "cones";
  /** Polygon fill from a numeric property: [value, colour] stops, linearly interpolated. */
  fillScale?: {
    property: string;
    stops: readonly (readonly [number, string])[];
    /** [value, opacity] stops; low values can fade out so only what matters stands out. */
    opacity?: readonly (readonly [number, number])[];
  };
  /** Colour by a categorical feature property; unknown values fall back to `color`. */
  colorBy?: { property: string; values: Readonly<Record<string, string>> };
  /** Use a colour carried by each feature (e.g. a cable's own colour) when present. */
  colorProperty?: string;
  /** Scale radius linearly with a 0..1 property (e.g. severity) between min and max. */
  radiusBy?: { property: string; min: number; max: number };
  /** Rotate an arrow marker by this property (degrees). */
  rotationProperty?: string;
  /** Recolour features whose `property` is in the watched set. */
  highlight?: { property: string; color: string };
}

/** What kind of watchable thing a layer's features are, if any. */
export type WatchableKind = "aircraft" | "vessel";

interface BaseLayer {
  id: string;
  label: string;
  group: LayerGroup;
  refreshMs: number;
  defaultEnabled: boolean;
  /** One line shown on hover, e.g. data caveats or licence. */
  note?: string;
  /** Below this zoom the layer is not requested (its upstream only serves small areas). */
  minZoom?: number;
}

/**
 * A map layer is a plug-in: an id, a loader and a style. Adding a data source
 * to the map means writing one of these and registering it — nothing in the
 * map component changes.
 */
export interface FeatureLayer extends BaseLayer {
  kind?: "features";
  style: LayerStyle;
  /** Present when features can be added to the watchlist from their popup. */
  watchable?: WatchableKind;
  /** Features have a flight track the popup can show. */
  tracks?: boolean;
  load(ctx: LayerContext): Promise<LayerFeatures>;
}

export interface RasterMapLayer extends BaseLayer {
  kind: "raster";
  load(ctx: LayerContext): Promise<RasterData>;
}

export type MapLayer = FeatureLayer | RasterMapLayer;

export const isRasterLayer = (layer: MapLayer): layer is RasterMapLayer => layer.kind === "raster";
