import type { ChokepointTraffic, Quote } from "@/lib/api/types";

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Thousands are grouped with a narrow no-break space (SI style): "7 743". */
export const THIN = "\u202f";

export function priceDigits(value: number): number {
  const abs = Math.abs(value);
  return abs >= 1000 ? 0 : abs >= 100 ? 1 : abs >= 10 ? 2 : 4;
}

/** Enough digits to see a move: FX needs four, indices none. */
export function formatPrice(value: number, digits = priceDigits(value)): string {
  return value
    .toLocaleString("en", { minimumFractionDigits: digits, maximumFractionDigits: digits })
    .replaceAll(",", THIN);
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${value >= 1e5 ? compact.format(value) : formatPrice(value)}`;
}

/** "+1.73" / "−0.02": a true minus sign, so columns of changes align. */
export function formatSigned(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const text = formatPrice(Math.abs(value), digits);
  return value > 0 ? `+${text}` : value < 0 ? `\u2212${text}` : text;
}

/** "▲ 1.24 %" / "▼ 0.50 %" — the arrow carries the direction, not only the colour. */
export function formatChange(pct: number | null | undefined): {
  text: string;
  tone: "up" | "down" | "flat";
} {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return { text: "—", tone: "flat" };
  if (Math.abs(pct) < 0.005) return { text: "0.00 %", tone: "flat" };
  const tone = pct > 0 ? "up" : "down";
  return { text: `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(2)} %`, tone };
}

export function quoteLabel(quote: Quote): string {
  const unit = quote.instrument.unit;
  if (unit === "%") return `${quote.price.toFixed(2)} %`; // rates are read to the basis point
  return unit && unit !== "pts" ? `${formatPrice(quote.price)} ${unit}` : formatPrice(quote.price);
}

export type TrafficStatus = "halted" | "severe" | "reduced" | "normal" | "busier" | "unknown";

/** Headline comparison is the same week last year (see the backend's chokepoints module). */
export function trafficStatus(c: ChokepointTraffic): TrafficStatus {
  const change = c.change_vs_last_year_pct;
  if (change === null || change === undefined) return "unknown";
  if (c.last_7d_avg === 0 || change <= -90) return "halted";
  if (change <= -50) return "severe";
  if (change <= -15) return "reduced";
  if (change < 15) return "normal";
  return "busier";
}

export const TRAFFIC_LABELS: Record<TrafficStatus, string> = {
  halted: "Traffic near zero",
  severe: "Severely reduced",
  reduced: "Reduced",
  normal: "Normal",
  busier: "Busier than usual",
  unknown: "No baseline",
};
