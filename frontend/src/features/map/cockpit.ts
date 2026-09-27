/**
 * The cockpit view: the camera rides a tracked aircraft. Everything here is
 * pure so the geometry is testable; the Cesium canvas only applies it.
 *
 * Between two reports the position is extrapolated along the last reported
 * track and speed, for smooth motion. The HUD always shows how old the last
 * report is, so an extrapolated position is never mistaken for a fix.
 */

const EARTH_RADIUS_M = 6_371_008.8;
const RAD = Math.PI / 180;
/** Past this, extrapolation stops: the aircraft is shown where it was last reported. */
export const MAX_EXTRAPOLATION_S = 60;
export const CONTACT_RADIUS_KM = 250;

export interface Fix {
  id: string;
  callsign: string;
  lat: number;
  lon: number;
  altitudeM: number | null;
  speedMs: number | null;
  headingDeg: number | null;
  /** When the feed reported this position (ms since epoch). */
  at: number;
}

export interface Contact {
  id: string;
  callsign: string;
  distanceKm: number;
  /** Compass bearing from our aircraft, degrees. */
  bearingDeg: number;
  /** Relative to our nose: -180..180, negative is to the left. */
  relativeDeg: number;
  /** Their altitude minus ours, metres; null if either is unknown. */
  altitudeDeltaM: number | null;
}

export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * RAD;
  const dLon = (lon2 - lon1) * RAD;
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dLon / 2) ** 2;
  return (2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)))) / 1000;
}

export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const y = Math.sin((lon2 - lon1) * RAD) * Math.cos(lat2 * RAD);
  const x =
    Math.cos(lat1 * RAD) * Math.sin(lat2 * RAD) -
    Math.sin(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.cos((lon2 - lon1) * RAD);
  return (Math.atan2(y, x) / RAD + 360) % 360;
}

/** Signed smallest angle from ``from`` to ``to``, in -180..180. */
export function angleDelta(from: number, to: number): number {
  return ((((to - from) % 360) + 540) % 360) - 180;
}

/** Where the aircraft would be ``now`` if it held its last reported track and speed. */
export function extrapolate(fix: Fix, now: number): { lat: number; lon: number } {
  const dt = Math.min(MAX_EXTRAPOLATION_S, Math.max(0, (now - fix.at) / 1000));
  if (!fix.speedMs || fix.headingDeg === null || dt === 0) return { lat: fix.lat, lon: fix.lon };
  const d = (fix.speedMs * dt) / EARTH_RADIUS_M;
  const b = fix.headingDeg * RAD;
  const p1 = fix.lat * RAD;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 =
    fix.lon * RAD +
    Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return { lat: p2 / RAD, lon: ((l2 / RAD + 540) % 360) - 180 };
}

/** Other aircraft within ``radiusKm``, nearest first. */
export function contacts(
  self: Fix,
  others: readonly Fix[],
  radiusKm = CONTACT_RADIUS_KM,
  limit = 8,
): Contact[] {
  const out: Contact[] = [];
  for (const o of others) {
    if (o.id === self.id) continue;
    const distance = distanceKm(self.lat, self.lon, o.lat, o.lon);
    if (distance > radiusKm) continue;
    const bearing = bearingDeg(self.lat, self.lon, o.lat, o.lon);
    out.push({
      id: o.id,
      callsign: o.callsign,
      distanceKm: distance,
      bearingDeg: bearing,
      relativeDeg: angleDelta(self.headingDeg ?? 0, bearing),
      altitudeDeltaM:
        self.altitudeM !== null && o.altitudeM !== null ? o.altitudeM - self.altitudeM : null,
    });
  }
  return out.sort((a, b) => a.distanceKm - b.distanceKm).slice(0, limit);
}

/** A fix from an aircraft feature's properties and position. */
export function fixFrom(
  id: string,
  properties: Record<string, unknown>,
  lat: number,
  lon: number,
  at: number,
): Fix {
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  return {
    id,
    callsign: String(properties.title ?? id),
    lat,
    lon,
    altitudeM: num(properties.altitude_m),
    speedMs: num(properties.velocity_ms),
    headingDeg: properties.heading_stated === false ? null : num(properties.heading_deg),
    at,
  };
}

/** Eye height: the reported altitude, never below the ground clearance of a cockpit. */
export function eyeHeight(fix: Fix): number {
  return Math.max(fix.altitudeM ?? 0, 0) + 30;
}
