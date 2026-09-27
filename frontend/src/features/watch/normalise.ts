import type { WatchKind } from "@/lib/api/types";

/** Client mirror of the server's normalisers, for instant feedback while typing. */
const RULES: Record<WatchKind, { clean(raw: string): string; pattern: RegExp; error: string }> = {
  aircraft: {
    clean: (s) => s.trim().toLowerCase(),
    pattern: /^[0-9a-f]{6}$/,
    error: "An ICAO 24-bit address is 6 hexadecimal characters.",
  },
  vessel: {
    clean: (s) => s.trim(),
    pattern: /^\d{9}$/,
    error: "An MMSI has exactly 9 digits.",
  },
  ticker: {
    clean: (s) => s.trim().toUpperCase(),
    pattern: /^\^?[A-Z0-9][A-Z0-9.\-=]{0,19}$/,
    error: "Tickers use letters, digits and ^ . = -",
  },
  country: {
    clean: (s) => s.trim().toUpperCase(),
    pattern: /^[A-Z]{2}$/,
    error: "Use a 2-letter ISO code, e.g. TW.",
  },
  keyword: {
    clean: (s) => s.trim().split(/\s+/).join(" "),
    pattern: /^\S(?:.{0,98}\S)?$/,
    error: "A keyword is 1 to 100 characters.",
  },
};

export const WATCH_KIND_LABELS: Record<WatchKind, string> = {
  aircraft: "Aircraft",
  vessel: "Ship",
  ticker: "Ticker",
  country: "Country",
  keyword: "Keyword",
};

export const WATCH_PLACEHOLDERS: Record<WatchKind, string> = {
  aircraft: "ICAO 24-bit, e.g. 3C6444",
  vessel: "MMSI, 9 digits",
  ticker: "e.g. BZ=F, XOM",
  country: "ISO code, e.g. TW",
  keyword: "word or phrase",
};

export type Normalised = { ok: true; value: string } | { ok: false; error: string };

export function normaliseWatch(kind: WatchKind, raw: string): Normalised {
  if (!raw.trim()) return { ok: false, error: "Enter a value first." };
  const rule = RULES[kind];
  const value = rule.clean(raw);
  return rule.pattern.test(value) ? { ok: true, value } : { ok: false, error: rule.error };
}
