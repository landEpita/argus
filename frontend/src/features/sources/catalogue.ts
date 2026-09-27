import type { Health } from "@/lib/api/types";

/** What each upstream powers, for people: the health API only knows provider ids. */
interface Entry {
  name: string;
  powers: string;
  refresh: string;
}

const CATALOGUE: Record<string, Entry> = {
  opensky: { name: "OpenSky", powers: "Flights, flight tracks", refresh: "15 s" },
  adsblol: { name: "adsb.lol", powers: "Flights (fallback), military", refresh: "15 s" },
  usgs: { name: "USGS", powers: "Earthquakes", refresh: "1 min" },
  eonet: { name: "NASA EONET", powers: "Natural events", refresh: "15 min" },
  gdacs: { name: "GDACS", powers: "Disaster alerts", refresh: "15 min" },
  gdelt: { name: "GDELT", powers: "Reported violence (unverified)", refresh: "5 min" },
  firms: { name: "NASA FIRMS", powers: "Fire hotspots", refresh: "15 min" },
  ubilling: { name: "Ukraine air-raid alerts", powers: "Air-raid alerts", refresh: "30 s" },
  launchlibrary: { name: "Launch Library 2", powers: "Space launches", refresh: "1 h" },
  celestrak: { name: "CelesTrak", powers: "Satellites", refresh: "2 h" },
  aisstream: { name: "AISStream", powers: "Ships (AIS)", refresh: "live" },
  ioda: { name: "IODA", powers: "Internet outages", refresh: "10 min" },
  "cisa-kev": { name: "CISA KEV", powers: "Exploited vulnerabilities", refresh: "6 h" },
  telegram: { name: "Telegram", powers: "OSINT channels (unverified)", refresh: "5 min" },
  overpass: {
    name: "Overpass (OpenStreetMap)",
    powers: "Military sites, data centres, nuclear plants",
    refresh: "24 h",
  },
  telegeography: { name: "TeleGeography", powers: "Submarine cables", refresh: "24 h" },
  rainviewer: { name: "RainViewer", powers: "Precipitation radar", refresh: "5 min" },
  news: { name: "News outlets (RSS)", powers: "News stories", refresh: "5 min" },
  yahoo: { name: "Yahoo Finance", powers: "Quotes, price history", refresh: "1 min" },
  coingecko: { name: "CoinGecko", powers: "Crypto prices", refresh: "2 min" },
  binance: { name: "Binance", powers: "Funding rates", refresh: "5 min" },
  okx: { name: "OKX", powers: "Funding (fallback), liquidations", refresh: "2 min" },
  polymarket: { name: "Polymarket", powers: "Prediction markets", refresh: "5 min" },
  "alternative-me": { name: "alternative.me", powers: "Crypto Fear & Greed", refresh: "1 h" },
  "us-treasury": { name: "US Treasury", powers: "Yield curve", refresh: "6 h" },
  forexfactory: { name: "Forex Factory", powers: "Economic calendar", refresh: "1 h" },
  portwatch: { name: "IMF PortWatch", powers: "Chokepoint traffic", refresh: "6 h" },
  eia: { name: "EIA", powers: "US energy inventories", refresh: "6 h" },
};

/** Keys the server can be given; without them the capability is not registered. */
export interface KeyInfo {
  source: string;
  name: string;
  capability: string;
  setting: string;
  unlocks: string;
  how: string;
  url: string;
  /** Works without a key, with limits. */
  optional?: boolean;
}

export const KEYS: readonly KeyInfo[] = [
  {
    source: "aisstream",
    name: "AISStream",
    capability: "maritime.vessel_positions",
    setting: "ARGUS_AISSTREAM_API_KEY",
    unlocks: "Ships · AIS: vessels live, with name, MMSI, destination and speed.",
    how: "Free account at aisstream.io",
    url: "https://aisstream.io",
  },
  {
    source: "firms",
    name: "NASA FIRMS",
    capability: "events.fires",
    setting: "ARGUS_FIRMS_MAP_KEY",
    unlocks: "Fire hotspots: satellite heat detections of the last 24 h.",
    how: "Free MAP_KEY from NASA",
    url: "https://firms.modaps.eosdis.nasa.gov/api/map_key/",
  },
  {
    source: "eia",
    name: "EIA",
    capability: "energy.inventory_series",
    setting: "ARGUS_EIA_API_KEY",
    unlocks: "US energy inventories. Without a key, a shared demo key allows a few calls an hour.",
    how: "Free key from the EIA",
    url: "https://www.eia.gov/opendata/register.php",
    optional: true,
  },
];

export type SourceStatus = "ok" | "down" | "stale" | "needs-key" | "idle";

export interface SourceRow {
  id: string;
  name: string;
  powers: string;
  refresh: string;
  status: SourceStatus;
  lastSuccessAgeS: number | null;
  lastError: string | null;
  /** Mirrors or outlets behind one row. */
  members: number;
}

const HEALTH_STATUS: Record<Health["sources"][number]["status"], SourceStatus> = {
  ok: "ok",
  failing: "down",
  stale: "stale",
  idle: "idle",
};
const SEVERITY: SourceStatus[] = ["down", "stale", "needs-key", "idle", "ok"];

/** "news:bbc" → "news", "overpass-de" → "overpass". */
export function familyOf(source: string): string {
  if (source.startsWith("news:")) return "news";
  if (source.startsWith("overpass-")) return "overpass";
  return source;
}

/**
 * One row per upstream family, worst status first. Keyed sources that are not
 * registered appear as "needs key"; infrastructure checks (redis) are left out.
 */
export function sourceRows(
  health: Health | null,
  capabilities: Readonly<Record<string, readonly string[]>> | null,
): SourceRow[] {
  const rows = new Map<string, SourceRow>();
  for (const s of health?.sources ?? []) {
    const id = familyOf(s.source);
    const entry = CATALOGUE[id];
    if (!entry) continue;
    const status = HEALTH_STATUS[s.status];
    const row = rows.get(id);
    if (!row) {
      rows.set(id, {
        id,
        ...entry,
        status,
        lastSuccessAgeS: s.last_success_age_s,
        lastError: s.last_error,
        members: 1,
      });
      continue;
    }
    row.members += 1;
    if (SEVERITY.indexOf(status) < SEVERITY.indexOf(row.status)) {
      row.status = status;
      row.lastError = s.last_error ?? row.lastError;
    }
    if (s.last_success_age_s !== null) {
      row.lastSuccessAgeS = Math.min(row.lastSuccessAgeS ?? Infinity, s.last_success_age_s);
    }
  }
  if (capabilities) {
    for (const key of KEYS) {
      if (!key.optional && !(key.capability in capabilities) && !rows.has(key.source)) {
        const entry = CATALOGUE[key.source] as Entry;
        rows.set(key.source, {
          id: key.source,
          ...entry,
          status: "needs-key",
          lastSuccessAgeS: null,
          lastError: "API key missing",
          members: 1,
        });
      }
    }
  }
  return [...rows.values()].sort(
    (a, b) =>
      SEVERITY.indexOf(a.status) - SEVERITY.indexOf(b.status) || a.name.localeCompare(b.name),
  );
}

export function summarise(rows: readonly SourceRow[]): Record<SourceStatus, number> {
  const out: Record<SourceStatus, number> = { ok: 0, down: 0, stale: 0, "needs-key": 0, idle: 0 };
  for (const r of rows) out[r.status] += 1;
  return out;
}

export function keyConfigured(
  key: KeyInfo,
  capabilities: Readonly<Record<string, readonly string[]>> | null,
): boolean | null {
  if (!capabilities) return null;
  return key.capability in capabilities;
}
