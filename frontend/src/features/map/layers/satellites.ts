import type { SatelliteGroup, SatellitePosition } from "@/lib/api/types";
import { collection, pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

export function satellitesToFeatures(satellites: readonly SatellitePosition[]): LayerFeatures {
  return collection(
    satellites.map((s) =>
      pointFeature(String(s.norad_id), s.position.lon, s.position.lat, {
        title: s.name,
        norad_id: s.norad_id,
        altitude_km: s.altitude_km,
        speed_kms: s.speed_kms,
        elements_age_days: s.elements_age_days,
        at: s.at,
      }),
    ),
  );
}

function satelliteLayer(
  group: SatelliteGroup,
  label: string,
  color: string,
  options: { defaultEnabled?: boolean; radius?: number; note?: string } = {},
): FeatureLayer {
  return {
    id: `sat-${group}`,
    label,
    group: "space",
    refreshMs: 10_000,
    defaultEnabled: options.defaultEnabled ?? false,
    note: options.note,
    style: { color, radius: options.radius ?? 3 },
    async load({ api, signal }) {
      const { items } = await api.satellites(group, signal);
      return satellitesToFeatures(items);
    },
  };
}

export const satelliteLayers: readonly FeatureLayer[] = [
  satelliteLayer("stations", "Space stations", "#fde047", { defaultEnabled: true, radius: 5 }),
  satelliteLayer("visual", "Brightest satellites", "#e2e8f0"),
  satelliteLayer("gps-ops", "GPS constellation", "#34d399"),
  satelliteLayer("galileo", "Galileo constellation", "#60a5fa"),
  satelliteLayer("weather", "Weather satellites", "#7dd3fc"),
  satelliteLayer("military", "Military satellites", "#fb923c"),
  satelliteLayer("starlink", "Starlink", "#a5b4fc", { radius: 1.5, note: "~9,000 objects" }),
];
