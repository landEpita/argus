export interface SparkPoint {
  at: string;
  score: number;
}

/**
 * SVG path for a 0..100 series over time. Time is proportional (gaps in the
 * snapshots show as longer segments, not as a compressed line).
 */
export function sparklinePath(
  points: readonly SparkPoint[],
  width: number,
  height: number,
): string {
  const parsed = points
    .map((p) => ({ t: Date.parse(p.at), v: Math.min(100, Math.max(0, p.score)) }))
    .filter((p) => !Number.isNaN(p.t))
    .sort((a, b) => a.t - b.t);
  if (parsed.length === 0) return "";
  const first = parsed[0]?.t ?? 0;
  const span = (parsed[parsed.length - 1]?.t ?? first) - first || 1;
  return parsed
    .map((p, i) => {
      const x = parsed.length === 1 ? width : ((p.t - first) / span) * width;
      const y = height - (p.v / 100) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
