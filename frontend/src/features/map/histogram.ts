import type { LayerFeatures } from "./layers/types";

export interface Bin {
  start: number;
  verified: number;
  unverified: number;
}

export const HISTOGRAM_HOURS = 6;
export const HISTOGRAM_BINS = 24; // 15 minutes each

/**
 * Events per 15 minutes over the last 6 hours, from the layers on screen.
 * Only features carrying ``occurred_at`` count; layers listed in
 * ``unverifiedLayers`` (press-coded) are stacked separately.
 */
export function binEvents(
  layers: ReadonlyMap<string, LayerFeatures>,
  unverifiedLayers: ReadonlySet<string>,
  now: number,
  hours = HISTOGRAM_HOURS,
  bins = HISTOGRAM_BINS,
): Bin[] {
  const span = hours * 3_600_000;
  const width = span / bins;
  const start = now - span;
  const out: Bin[] = Array.from({ length: bins }, (_, i) => ({
    start: start + i * width,
    verified: 0,
    unverified: 0,
  }));
  for (const [id, data] of layers) {
    const unverified = unverifiedLayers.has(id);
    for (const f of data.features) {
      const at = Date.parse(String(f.properties.occurred_at ?? ""));
      if (Number.isNaN(at) || at < start || at > now) continue;
      const bin = out[Math.min(bins - 1, Math.floor((at - start) / width))];
      if (!bin) continue;
      if (unverified) bin.unverified += 1;
      else bin.verified += 1;
    }
  }
  return out;
}
