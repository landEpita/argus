import type { CryptoAsset, Quote } from "@/lib/api/types";
import { groupOf, type MarketGroup } from "./groups";

/** One line of the markets table, whatever feed it came from. */
export interface MarketRow {
  /** Yahoo symbol, used for the asset chart. */
  symbol: string;
  name: string;
  unit: string | null;
  group: MarketGroup;
  price: number;
  change: number | null;
  changePct: number | null;
  dayLow: number | null;
  dayHigh: number | null;
  history: readonly number[];
  source: string;
}

export function quoteRow(q: Quote): MarketRow {
  return {
    symbol: q.instrument.symbol,
    name: q.instrument.name,
    unit: q.instrument.unit,
    group: groupOf(q.instrument),
    price: q.price,
    change: q.change,
    changePct: q.change_pct,
    dayLow: q.day_low,
    dayHigh: q.day_high,
    history: q.history,
    source: q.source,
  };
}

/** Crypto rows come from CoinGecko (24 h change); their chart uses Yahoo's "BTC-USD". */
export function cryptoRow(c: CryptoAsset): MarketRow {
  const pct = c.change_24h_pct;
  return {
    symbol: `${c.symbol.toUpperCase()}-USD`,
    name: c.name,
    unit: "USD",
    group: "Crypto",
    price: c.price_usd,
    change: pct === null ? null : c.price_usd - c.price_usd / (1 + pct / 100),
    changePct: pct,
    dayLow: null,
    dayHigh: null,
    history: [],
    source: c.source,
  };
}

/** Where the price sits in the session range, 0..100; null without a range. */
export function rangePosition(row: Pick<MarketRow, "price" | "dayLow" | "dayHigh">): number | null {
  const { price, dayLow: lo, dayHigh: hi } = row;
  if (lo === null || hi === null || hi <= lo) return null;
  return Math.round(Math.min(1, Math.max(0, (price - lo) / (hi - lo))) * 100);
}
