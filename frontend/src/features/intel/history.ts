import type { CountrySignal } from "@/lib/api/types";
import { COMPONENT_LABELS } from "./signals";

export interface HistoryBar {
  start: number;
  /** Mean score of the snapshots in the bucket, or null when there were none. */
  score: number | null;
}

/**
 * Hourly snapshots averaged into fixed buckets ending at `now`, so gaps show
 * as empty bars rather than a compressed line.
 */
export function bucketHistory(
  points: readonly { at: string; score: number }[],
  now: number,
  days = 7,
  buckets = 28,
): HistoryBar[] {
  const span = days * 86_400_000;
  const width = span / buckets;
  const start = now - span;
  const sums = Array.from({ length: buckets }, () => ({ total: 0, n: 0 }));
  for (const p of points) {
    const at = Date.parse(p.at);
    if (Number.isNaN(at) || at < start || at > now) continue;
    const bucket = sums[Math.min(buckets - 1, Math.floor((at - start) / width))];
    if (!bucket) continue;
    bucket.total += p.score;
    bucket.n += 1;
  }
  return sums.map((b, i) => ({
    start: start + i * width,
    score: b.n ? Math.round((b.total / b.n) * 10) / 10 : null,
  }));
}

/**
 * A plain-language summary composed from the figures only (no language model):
 * what contributes, what is missing, and how to read it.
 */
export function describeSignal(
  name: string,
  signal: CountrySignal | null,
  missing: string | null,
): string {
  if (!signal || signal.score === 0) {
    return `No disruptive signal about ${name} in the feeds right now.${missing ? ` ${missing}.` : ""}`;
  }
  const parts = signal.components
    .filter((c) => c.points > 0)
    .sort((a, b) => b.points - a.points)
    .map((c) => `${COMPONENT_LABELS[c.component].toLowerCase()} (${c.points} of ${c.max_points})`);
  const text = [
    `${name}'s signal index is ${signal.score.toFixed(0)} / 100, from ${parts.join(", ")}.`,
    signal.has_baseline
      ? "Violence and news are compared with the country's usual level."
      : "There is no baseline yet, so violence and news are counted in absolute terms, which favours countries with a large English-language press.",
  ];
  if (signal.components.some((c) => c.component === "reported_violence" && c.points > 0)) {
    text.push(
      "Reported violence comes from automated press coding: read it as a trend, not a count of facts.",
    );
  }
  if (missing) text.push(`${missing}.`);
  return text.join(" ");
}
