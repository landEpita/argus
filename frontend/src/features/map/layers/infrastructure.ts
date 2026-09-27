import type { CableNetwork, Facility, FacilityKind } from "@/lib/api/types";
import { collection, pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export function facilitiesToFeatures(facilities: readonly Facility[]): LayerFeatures {
  return collection(
    facilities.map((f) =>
      pointFeature(f.id, f.position.lon, f.position.lat, {
        title: f.name ?? "Unnamed site",
        subtype: f.subtype,
        operator: f.operator,
        url: f.url,
        source: "OpenStreetMap",
      }),
    ),
  );
}

export function cablesToFeatures(network: CableNetwork): LayerFeatures {
  return {
    type: "FeatureCollection",
    features: [
      ...network.cables.map((c) => ({
        type: "Feature" as const,
        id: c.id,
        geometry: {
          type: "MultiLineString" as const,
          coordinates: c.lines.map((line) => line.map(([lon, lat]) => [lon, lat])),
        },
        properties: { title: c.name, color: c.color, attribution: network.attribution },
      })),
      ...network.landing_points.map((p) =>
        pointFeature(p.id, p.position.lon, p.position.lat, {
          title: p.name,
          kind: "landing point",
        }),
      ),
    ],
  };
}

function facilityLayer(
  kind: FacilityKind,
  label: string,
  color: string,
  note: string,
): FeatureLayer {
  return {
    id: `facility-${kind}`,
    label,
    group: "infrastructure",
    refreshMs: 3_600_000,
    defaultEnabled: false,
    minZoom: 5,
    note,
    style: { color, radius: 4 },
    async load({ api, bbox, signal }) {
      const { items } = await api.facilities(kind, bbox, signal);
      return facilitiesToFeatures(items);
    },
  };
}

export const cablesLayer: FeatureLayer = {
  id: "submarine-cables",
  label: "Submarine cables",
  group: "infrastructure",
  refreshMs: 86_400_000,
  defaultEnabled: false,
  note: "© TeleGeography, CC BY-NC-SA 3.0 (non-commercial use)",
  style: { color: "#22d3ee", radius: 2, geometry: "mixed", colorProperty: "color" },
  async load({ api, signal }) {
    return cablesToFeatures(await api.cables(signal));
  },
};

export const infrastructureLayers: readonly FeatureLayer[] = [
  cablesLayer,
  facilityLayer(
    "military",
    "Military sites (OSM)",
    "#f97316",
    "Only what OpenStreetMap volunteers mapped; zoom in",
  ),
  facilityLayer("data-center", "Data centres (OSM)", "#a3e635", "OpenStreetMap; zoom in"),
  facilityLayer("nuclear-plant", "Nuclear power plants (OSM)", "#fde047", "OpenStreetMap; zoom in"),
];
