import type { RasterLayer } from "@/lib/api/types";
import type { RasterData, RasterMapLayer } from "./types";

export function toRasterData(layer: RasterLayer): RasterData {
  return {
    tiles: [...layer.tiles],
    tileSize: layer.tile_size,
    minZoom: layer.min_zoom,
    maxZoom: layer.max_zoom,
    attribution: layer.attribution,
    validAt: layer.valid_at,
    opacity: layer.opacity,
  };
}

export class RasterUnavailableError extends Error {
  constructor(id: string) {
    super(`raster layer '${id}' is not offered by the server right now`);
    this.name = "RasterUnavailableError";
  }
}

function rasterLayer(id: string, label: string, refreshMs: number, note?: string): RasterMapLayer {
  return {
    kind: "raster",
    id,
    label,
    group: "imagery",
    refreshMs,
    defaultEnabled: false,
    note,
    async load({ api, signal }) {
      const found = (await api.rasters(signal)).find((r) => r.id === id);
      if (!found) throw new RasterUnavailableError(id);
      return toRasterData(found);
    },
  };
}

export const imageryLayers: readonly RasterMapLayer[] = [
  rasterLayer(
    "weather-radar",
    "Precipitation radar",
    300_000,
    "RainViewer; detail stops at zoom 7",
  ),
  rasterLayer(
    "satellite-true-color",
    "Satellite imagery (yesterday)",
    3_600_000,
    "NASA GIBS, VIIRS",
  ),
  rasterLayer(
    "night-lights",
    "Night lights (yesterday)",
    3_600_000,
    "NASA GIBS, VIIRS day/night band",
  ),
];
