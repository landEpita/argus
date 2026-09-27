import type { Convergence, SignalKind } from "@/lib/api/types";
import { SIGNAL_KIND_LABELS } from "./layers/analysis";

/** Kinds that come from automated press coding: leads, never corroboration. */
export const UNVERIFIED_KINDS: ReadonlySet<SignalKind> = new Set(["reported_violence"]);

export interface SituationSignal {
  kind: SignalKind;
  label: string;
  count: number;
  unverified: boolean;
  examples: readonly string[];
}

export interface Situation {
  id: string;
  rank: number;
  title: string;
  place: string;
  signals: SituationSignal[];
  /** Distinct verified kinds: what actually corroborates. */
  corroborating: number;
  unverified: number;
  latest: string;
  center: { lat: number; lon: number };
}

export function corroborationLabel(s: Pick<Situation, "corroborating" | "unverified">): string {
  if (s.corroborating >= 2) return `${s.corroborating} independent kinds of signal agree`;
  if (s.corroborating === 1)
    return s.unverified ? "One verified kind, plus unverified reports" : "Single kind of signal";
  return "Unverified only — no corroboration";
}

/**
 * A convergence cell, as the "Right now" list presents it. The title names the
 * two strongest verified kinds; nothing is inferred beyond what the cell says.
 */
export function toSituation(
  c: Convergence,
  rank: number,
  countryName: (iso2: string) => string,
): Situation {
  const signals = c.kinds.map((k) => ({
    kind: k.kind,
    label: SIGNAL_KIND_LABELS[k.kind],
    count: k.count,
    unverified: UNVERIFIED_KINDS.has(k.kind),
    examples: k.examples,
  }));
  const verified = signals.filter((s) => !s.unverified);
  const lead = (verified.length ? verified : signals).slice(0, 2).map((s) => s.label);
  const coords = `${c.center.lat.toFixed(1)}°, ${c.center.lon.toFixed(1)}°`;
  return {
    id: c.id,
    rank,
    title: lead.join(" with ").replace(/^./, (x) => x.toUpperCase()),
    place: c.country ? `${countryName(c.country)} · ${coords}` : coords,
    signals,
    corroborating: verified.length,
    unverified: signals.length - verified.length,
    latest: c.latest,
    center: c.center,
  };
}
