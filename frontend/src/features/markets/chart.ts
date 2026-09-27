/** Geometry of the price chart, in a fixed viewBox the SVG stretches. */
export interface ChartGeometry {
  line: string;
  area: string;
  min: number;
  max: number;
  /** 0..100, from the top: where a price sits, for HTML overlays. */
  yPercent(value: number): number;
  /** Four evenly spaced gridline values. */
  grid: number[];
}

export const CHART_W = 600;
export const CHART_H = 230;
const PAD = 0.07; // headroom above and below the extremes

export function chartGeometry(values: readonly number[], w = CHART_W, h = CHART_H): ChartGeometry {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const y = (v: number) => h - ((v - min) / span) * h * (1 - 2 * PAD) - h * PAD;
  const x = (i: number) => (values.length < 2 ? w : (i / (values.length - 1)) * w);
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return {
    line,
    area: values.length ? `${line} ${w},${h} 0,${h}` : "",
    min,
    max,
    yPercent: (v) => (y(v) / h) * 100,
    grid: [0.12, 0.38, 0.64, 0.9].map((f) => min + span * f),
  };
}

/** Index of the bar under a pointer at `fraction` (0..1) of the chart width. */
export function indexAt(fraction: number, length: number): number {
  return Math.round(Math.min(1, Math.max(0, fraction)) * (length - 1));
}

/** Evenly spaced tick positions (indices) for the x axis. */
export function ticks(length: number, count = 5): number[] {
  if (length <= 1) return length ? [0] : [];
  return Array.from({ length: count }, (_, i) => Math.round((i / (count - 1)) * (length - 1)));
}
