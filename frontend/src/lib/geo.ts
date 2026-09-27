/** West, south, east, north — the order the backend expects. */
export interface BBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export function bboxToParam(box: BBox, precision = 4): string {
  return [box.west, box.south, box.east, box.north].map((v) => v.toFixed(precision)).join(",");
}

/** Clamp a viewport to valid WGS84 bounds (maps can report longitudes beyond ±180). */
export function clampBBox(box: BBox): BBox {
  const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);
  return {
    west: clamp(box.west, -180, 180),
    south: clamp(box.south, -90, 90),
    east: clamp(box.east, -180, 180),
    north: clamp(box.north, -90, 90),
  };
}

export interface MapPosition {
  center: { lat: number; lon: number };
  zoom: number;
}

/**
 * Round a camera position for storage: ~10 m and 1/100 zoom are invisible to
 * the user, and rounding keeps sub-pixel drift from producing needless saves.
 */
export function roundPosition(lat: number, lon: number, zoom: number): MapPosition {
  const round = (v: number, digits: number) => Number(v.toFixed(digits));
  return { center: { lat: round(lat, 4), lon: round(lon, 4) }, zoom: round(zoom, 2) };
}
