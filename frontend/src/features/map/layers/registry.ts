import type { LayerGroup, MapLayer } from "./types";

export interface LayerRegistry {
  all(): readonly MapLayer[];
  get(id: string): MapLayer | undefined;
  byGroup(): Map<LayerGroup, MapLayer[]>;
  defaults(): Set<string>;
}

export function createLayerRegistry(layers: readonly MapLayer[]): LayerRegistry {
  const byId = new Map<string, MapLayer>();
  for (const layer of layers) {
    if (byId.has(layer.id)) throw new Error(`duplicate layer id: ${layer.id}`);
    if (layer.refreshMs < 1_000) throw new Error(`layer ${layer.id}: refreshMs must be >= 1000`);
    byId.set(layer.id, layer);
  }

  return {
    all: () => layers,
    get: (id) => byId.get(id),
    byGroup() {
      const groups = new Map<LayerGroup, MapLayer[]>();
      for (const layer of layers) {
        const bucket = groups.get(layer.group) ?? [];
        bucket.push(layer);
        groups.set(layer.group, bucket);
      }
      return groups;
    },
    defaults: () => new Set(layers.filter((l) => l.defaultEnabled).map((l) => l.id)),
  };
}
