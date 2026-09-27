import type { Aircraft, AircraftTrack } from "@/lib/api/types";
import { collection, pointFeature, WATCH_HIGHLIGHT, watchKey } from "./features";
import type { FeatureLayer, LayerFeatures } from "./types";

/** The flights layer says when it is not showing everything, live. */
export function coverageNote(page: {
  coverage?: "box" | "world" | "regional";
  stale_age_s?: number | null;
  circle?: [number, number, number] | null;
}): { note: string; warn: boolean } | null {
  if (page.coverage === "regional" && page.circle) {
    return {
      note: `Only ${page.circle[2]} NM around the centre of the view (OpenSky unavailable)`,
      warn: true,
    };
  }
  if (page.stale_age_s != null) {
    const min = Math.round(page.stale_age_s / 60);
    return { note: `Snapshot from ${min} min ago (OpenSky quota reached)`, warn: true };
  }
  if (page.coverage === "world")
    return { note: "Worldwide snapshot, refreshed every few minutes", warn: false };
  return null;
}

export function aircraftToFeatures(aircraft: readonly Aircraft[]): LayerFeatures {
  return collection(
    aircraft.map((a) =>
      pointFeature(a.icao24, a.position.lon, a.position.lat, {
        title: a.callsign ?? a.icao24.toUpperCase(),
        watch_kind: "aircraft",
        watch_value: a.icao24,
        watch_key: watchKey("aircraft", a.icao24),
        icao24: a.icao24,
        registration: a.registration,
        type_code: a.type_code,
        origin_country: a.origin_country,
        altitude_m: a.altitude_m,
        velocity_ms: a.velocity_ms,
        heading_deg: a.heading_deg ?? 0,
        heading_stated: a.heading_deg != null,
        squawk: a.squawk,
        source: a.source,
      }),
    ),
  );
}

export const aircraftLayer: FeatureLayer = {
  id: "aircraft",
  label: "Live flights",
  group: "movement",
  refreshMs: 15_000,
  defaultEnabled: true,
  watchable: "aircraft",
  tracks: true,
  style: {
    color: "#38bdf8",
    radius: 3,
    rotationProperty: "heading_deg",
    highlight: WATCH_HIGHLIGHT,
  },
  async load({ api, bbox, signal }) {
    const page = await api.aircraft({ bbox }, signal);
    const features = aircraftToFeatures(page.items);
    const note = coverageNote(page);
    return note ? { ...features, meta: note } : features;
  },
};

export const militaryLayer: FeatureLayer = {
  id: "military",
  label: "Military aircraft",
  group: "movement",
  refreshMs: 30_000,
  defaultEnabled: false,
  watchable: "aircraft",
  tracks: true,
  note: "Flagged by the adsb.lol database; not exhaustive",
  style: {
    color: "#f59e0b",
    radius: 4,
    rotationProperty: "heading_deg",
    highlight: WATCH_HIGHLIGHT,
  },
  async load({ api, bbox, signal }) {
    const { items } = await api.military({ bbox }, signal);
    return aircraftToFeatures(items);
  },
};

/** A flight track as a line plus a marker where it started. */
export function trackToFeatures(track: AircraftTrack): LayerFeatures {
  const coordinates = track.points.map((p) => [p.position.lon, p.position.lat]);
  const first = track.points[0];
  if (!first || coordinates.length < 2) return collection([]);
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: `${track.icao24}-track`,
        geometry: { type: "LineString", coordinates },
        properties: { icao24: track.icao24, source: track.source },
      },
      pointFeature(`${track.icao24}-start`, first.position.lon, first.position.lat, {
        title: `${track.callsign ?? track.icao24} — first seen`,
        at: first.at,
      }),
    ],
  };
}
