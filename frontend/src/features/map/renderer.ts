import type {
  GeoJSONSource,
  LngLat,
  MapLayerMouseEvent,
  Map as MapLibreMap,
  RasterTileSource,
} from "maplibre-gl";
import type { LayerRegistry } from "./layers/registry";
import {
  type FeatureLayer,
  isRasterData,
  isRasterLayer,
  type LayerFeatures,
  type MapLayer,
  type RasterData,
  type RasterMapLayer,
} from "./layers/types";
import {
  ARROW_ICON,
  arrowImage,
  colorExpression,
  colorPaintProperty,
  rasterLayerSpec,
  rasterSource,
  sourceId,
  styleLayerIds,
  toMapLibreLayers,
} from "./render";
import type { LayerUpdate } from "./scheduler";

/** "realistic" is drawn by the Cesium renderer, not by this one. */
export type Projection = "mercator" | "globe" | "realistic";

export const TRACK_SOURCE = "argus-track";
const EMPTY: LayerFeatures = { type: "FeatureCollection", features: [] };

export type FeatureClickHandler = (
  layer: FeatureLayer,
  properties: Record<string, unknown>,
  at: LngLat,
) => void;

/**
 * Everything MapLibre-specific: sources, style layers, visibility, watched
 * highlight, the selected flight track and the projection.
 *
 * The React component only wires this to the scheduler and the stores, so the
 * rendering rules are testable with a fake map, and a second renderer (Cesium)
 * could implement the same surface.
 */
export class MapLibreRenderer {
  private readonly visible = new Set<string>();
  private readonly rasterTiles = new Map<string, string>();
  private installed = false;
  private projection: Projection = "mercator";

  constructor(
    private readonly map: MapLibreMap,
    private readonly registry: LayerRegistry,
  ) {}

  /** Call once the style has loaded. */
  install(enabled: ReadonlySet<string>, watched: readonly string[]): void {
    if (!this.map.hasImage(ARROW_ICON)) this.map.addImage(ARROW_ICON, arrowImage(), { sdf: true });
    for (const layer of this.drawOrder()) {
      if (enabled.has(layer.id)) this.visible.add(layer.id);
      if (isRasterLayer(layer)) continue; // added when its tile URLs arrive
      this.map.addSource(sourceId(layer.id), { type: "geojson", data: EMPTY });
      for (const spec of toMapLibreLayers(layer, this.visible.has(layer.id), watched)) {
        this.map.addLayer(spec);
      }
    }
    this.map.addSource(TRACK_SOURCE, { type: "geojson", data: EMPTY });
    this.map.addLayer({
      id: `${TRACK_SOURCE}-line`,
      source: TRACK_SOURCE,
      type: "line",
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#f472b6", "line-width": 2.5, "line-opacity": 0.9 },
    });
    this.map.addLayer({
      id: `${TRACK_SOURCE}-start`,
      source: TRACK_SOURCE,
      type: "circle",
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-color": "#f472b6", "circle-radius": 4 },
    });
    this.installed = true;
    this.map.setProjection({ type: this.maplibreProjection() });
  }

  onFeatureClick(handler: FeatureClickHandler): void {
    for (const layer of this.registry.all()) {
      if (isRasterLayer(layer)) continue;
      for (const id of styleLayerIds(layer)) {
        this.map.on("click", id, (e: MapLayerMouseEvent) => {
          const feature = e.features?.[0];
          if (feature) handler(layer, feature.properties as Record<string, unknown>, e.lngLat);
        });
        this.map.on("mouseenter", id, () => {
          this.map.getCanvas().style.cursor = "pointer";
        });
        this.map.on("mouseleave", id, () => {
          this.map.getCanvas().style.cursor = "";
        });
      }
    }
  }

  apply(update: LayerUpdate): void {
    const layer = this.registry.get(update.layerId);
    if (!layer) return;
    if (update.status === "zoom" && !isRasterLayer(layer)) {
      this.setFeatures(layer.id, EMPTY); // stale data from a closer zoom would mislead
    }
    if (update.status !== "ready") return;
    if (isRasterLayer(layer) && isRasterData(update.data)) {
      this.setRaster(layer, update.data);
    } else if (!isRasterData(update.data)) {
      this.setFeatures(layer.id, update.data);
    }
  }

  setVisible(layerId: string, on: boolean): void {
    if (on) this.visible.add(layerId);
    else this.visible.delete(layerId);
    const layer = this.registry.get(layerId);
    if (!layer) return;
    for (const id of styleLayerIds(layer)) {
      if (this.map.getLayer(id))
        this.map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    }
  }

  setWatched(keys: readonly string[]): void {
    for (const layer of this.registry.all()) {
      if (isRasterLayer(layer) || !layer.style.highlight) continue;
      const [id] = styleLayerIds(layer);
      if (id && this.map.getLayer(id)) {
        this.map.setPaintProperty(
          id,
          colorPaintProperty(layer),
          colorExpression(layer.style, keys),
        );
      }
    }
  }

  showTrack(features: LayerFeatures | null): void {
    this.map.getSource<GeoJSONSource>(TRACK_SOURCE)?.setData(features ?? EMPTY);
  }

  flyTo(lat: number, lon: number, zoom: number): void {
    this.map.flyTo({ center: [lon, lat], zoom, essential: true });
  }

  /** Safe before the style has loaded: the choice is applied by `install`. */
  setProjection(projection: Projection): void {
    this.projection = projection;
    if (this.installed) this.map.setProjection({ type: this.maplibreProjection() });
  }

  private maplibreProjection(): "mercator" | "globe" {
    return this.projection === "mercator" ? "mercator" : "globe";
  }

  private setFeatures(layerId: string, data: LayerFeatures): void {
    this.map.getSource<GeoJSONSource>(sourceId(layerId))?.setData(data);
  }

  private setRaster(layer: RasterMapLayer, data: RasterData): void {
    const signature = data.tiles.join("|");
    const existing = this.map.getSource<RasterTileSource>(sourceId(layer.id));
    if (existing) {
      if (this.rasterTiles.get(layer.id) !== signature) existing.setTiles(data.tiles);
    } else {
      this.map.addSource(sourceId(layer.id), rasterSource(data));
      // Imagery goes under every data layer so points stay readable.
      this.map.addLayer(
        rasterLayerSpec(layer, this.visible.has(layer.id), data.opacity),
        this.firstFeatureLayerId(),
      );
    }
    this.rasterTiles.set(layer.id, signature);
  }

  /** Areas first (bottom), then lines and points, so points stay clickable over fills. */
  private drawOrder(): MapLayer[] {
    const all = [...this.registry.all()];
    const isArea = (l: MapLayer) => !isRasterLayer(l) && l.style.geometry === "polygon";
    return [...all.filter(isArea), ...all.filter((l) => !isArea(l))];
  }

  private firstFeatureLayerId(): string | undefined {
    const first = this.drawOrder().find((l: MapLayer) => !isRasterLayer(l));
    return first ? styleLayerIds(first)[0] : undefined;
  }
}
