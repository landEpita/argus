import type { Feature, Polygon } from "geojson";
import type { Camera, CameraCollection } from "@/lib/api/types";
import { pointFeature } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

/** Drawn cone: the facing is the operator's; its width and reach are illustrative. */
export const CONE_HALF_ANGLE_DEG = 25;
export const CONE_REACH_M = 350;

const EARTH_RADIUS_M = 6_371_008.8;
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

export const NETWORK_LABELS: Record<Camera["network"], string> = {
  tfl: "Transport for London",
  fintraffic: "Fintraffic",
  drivebc: "DriveBC",
  nsw: "Transport for NSW",
  deldot: "DelDOT",
};

/** The point ``distanceM`` from (lat, lon) along ``bearingDeg`` (great circle). */
export function destination(
  lat: number,
  lon: number,
  bearingDeg: number,
  distanceM: number,
): [number, number] {
  const rad = Math.PI / 180;
  const d = distanceM / EARTH_RADIUS_M;
  const b = bearingDeg * rad;
  const p1 = lat * rad;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 =
    lon * rad +
    Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [l2 / rad, p2 / rad];
}

export function viewCone(lat: number, lon: number, heading: number): Polygon {
  const arc: [number, number][] = [];
  for (let step = -CONE_HALF_ANGLE_DEG; step <= CONE_HALF_ANGLE_DEG; step += 5) {
    arc.push(destination(lat, lon, heading + step, CONE_REACH_M));
  }
  return { type: "Polygon", coordinates: [[[lon, lat], ...arc, [lon, lat]]] };
}

export function facingLabel(heading: number | null | undefined): string {
  if (heading === null || heading === undefined) return "not stated by the operator";
  return `${COMPASS[Math.round(heading / 45) % 8]} (${Math.round(heading)}°)`;
}

export function camerasToFeatures(page: CameraCollection): LayerFeatures {
  const features: LayerFeatures["features"] = [];
  for (const cam of page.items) {
    const { lat, lon } = cam.position;
    const properties = {
      title: cam.name,
      camera: cam.id,
      facing: facingLabel(cam.heading_deg),
      view: cam.description,
      feed: cam.feed,
      media_url: cam.url,
      still_url: cam.still_url,
      source: NETWORK_LABELS[cam.network],
    };
    if (cam.heading_deg !== null && cam.heading_deg !== undefined) {
      const cone: Feature<Polygon, Record<string, unknown>> = {
        type: "Feature",
        id: `${cam.id}#cone`,
        geometry: viewCone(lat, lon, cam.heading_deg),
        properties,
      };
      features.push(cone);
    }
    features.push(pointFeature(cam.id, lon, lat, properties));
  }
  const missing = page.unavailable.map((n) => NETWORK_LABELS[n]);
  return {
    type: "FeatureCollection",
    features,
    count: page.items.length,
    ...(missing.length > 0 && {
      meta: { note: `Not reachable: ${missing.join(", ")}`, warn: true },
    }),
  };
}

export const camerasLayer: FeatureLayer = {
  id: "open-cameras",
  label: "Open cameras",
  group: "infrastructure",
  refreshMs: 3_600_000,
  defaultEnabled: false,
  note:
    "Public road cameras from London, Finland, British Columbia, New South Wales and Delaware. " +
    "Cones show the facing the operator states; their width and reach are illustrative.",
  style: { color: "#facc15", radius: 4, geometry: "cones" },
  async load({ api, bbox, signal }) {
    return camerasToFeatures(await api.cameras(bbox, signal));
  },
};
