import type { Instrument } from "@/lib/api/types";

export const MARKET_GROUPS = [
  "Energy",
  "Metals & agriculture",
  "Indices",
  "FX & rates",
  "Crypto",
] as const;
export type MarketGroup = (typeof MARKET_GROUPS)[number];

const ENERGY_UNITS = new Set(["USD/bbl", "USD/MMBtu", "EUR/MWh"]);

export function groupOf(instrument: Pick<Instrument, "asset_class" | "unit">): MarketGroup {
  switch (instrument.asset_class) {
    case "commodity":
      return instrument.unit && ENERGY_UNITS.has(instrument.unit)
        ? "Energy"
        : "Metals & agriculture";
    case "fx":
    case "rate":
      return "FX & rates";
    case "crypto":
      return "Crypto";
    default:
      return "Indices";
  }
}

/** Items grouped in `MARKET_GROUPS` order; empty groups are left out. */
export function byGroup<T>(
  items: readonly T[],
  group: (item: T) => MarketGroup,
): [MarketGroup, T[]][] {
  return MARKET_GROUPS.map(
    (g) => [g, items.filter((i) => group(i) === g)] as [MarketGroup, T[]],
  ).filter(([, list]) => list.length > 0);
}
