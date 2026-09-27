import { aircraftLayer, militaryLayer } from "./aircraft";
import { convergenceLayer, countryIndexLayer } from "./analysis";
import { camerasLayer } from "./cameras";
import { chokepointLayer } from "./chokepoints";
import { eventLayers } from "./events";
import { imageryLayers } from "./imagery";
import { infrastructureLayers } from "./infrastructure";
import { createLayerRegistry } from "./registry";
import { satelliteLayers } from "./satellites";
import { vesselLayer } from "./vessels";

/** The single list of layers the map knows about. Register new layers here. */
export const layerRegistry = createLayerRegistry([
  aircraftLayer,
  militaryLayer,
  vesselLayer,
  ...satelliteLayers,
  ...eventLayers,
  ...infrastructureLayers,
  camerasLayer,
  chokepointLayer,
  countryIndexLayer,
  convergenceLayer,
  ...imageryLayers,
]);

export type {
  FeatureLayer,
  LayerContext,
  LayerFeatures,
  LayerGroup,
  MapLayer,
  RasterMapLayer,
} from "./types";
