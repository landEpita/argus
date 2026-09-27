import { describe, expect, it } from "vitest";
import { chartGeometry, indexAt, ticks } from "./chart";
import { byGroup, groupOf } from "./groups";
import { EXCHANGES, formatDuration, sessionState } from "./sessions";

describe("market groups", () => {
  it("files instruments by what moves them together", () => {
    expect(groupOf({ asset_class: "commodity", unit: "USD/bbl" })).toBe("Energy");
    expect(groupOf({ asset_class: "commodity", unit: "EUR/MWh" })).toBe("Energy");
    expect(groupOf({ asset_class: "commodity", unit: "USD/oz" })).toBe("Metals & agriculture");
    expect(groupOf({ asset_class: "rate", unit: "%" })).toBe("FX & rates");
    expect(groupOf({ asset_class: "volatility", unit: "pts" })).toBe("Indices");
    expect(groupOf({ asset_class: "crypto", unit: null })).toBe("Crypto");
    const grouped = byGroup(["Indices", "Energy", "Indices"] as const, (g) => g);
    expect(grouped).toEqual([
      ["Energy", ["Energy"]],
      ["Indices", ["Indices", "Indices"]],
    ]);
  });
});

describe("sessions", () => {
  const us = EXCHANGES.find((e) => e.name === "US");
  if (!us) throw new Error("no US exchange");

  it("is open during New York hours", () => {
    // Monday 28 Sept 2026, 15:00 UTC = 11:00 in New York (EDT).
    expect(sessionState(us, new Date("2026-09-28T15:00:00Z"))).toEqual({
      name: "US",
      open: true,
      minutesUntilChange: 5 * 60,
    });
  });

  it("counts to Monday's open over the weekend", () => {
    // Saturday 26 Sept, 18:00 UTC = 14:00 EDT; Monday 09:30 is 43 h 30 min away.
    const s = sessionState(us, new Date("2026-09-26T18:00:00Z"));
    expect(s.open).toBe(false);
    expect(s.minutesUntilChange).toBe(43 * 60 + 30);
    expect(formatDuration(s.minutesUntilChange)).toBe("1 d 19 h");
  });

  it("opens later the same day before the bell", () => {
    // Monday 12:00 UTC = 08:00 EDT.
    const s = sessionState(us, new Date("2026-09-28T12:00:00Z"));
    expect(s).toMatchObject({ open: false, minutesUntilChange: 90 });
    expect(formatDuration(90)).toBe("1 h 30 min");
    expect(formatDuration(5)).toBe("5 min");
  });
});

describe("chart", () => {
  it("maps prices into the viewBox with headroom", () => {
    const g = chartGeometry([10, 20, 15], 100, 100);
    expect(g.line).toBe("0.0,93.0 50.0,7.0 100.0,50.0");
    expect(g.area).toBe(`${g.line} 100,100 0,100`);
    expect(g.yPercent(20)).toBeCloseTo(7);
    expect(g.grid).toHaveLength(4);
    expect(chartGeometry([5, 5], 10, 10).line).toBe("0.0,9.3 10.0,9.3");
  });

  it("finds the bar under the pointer and spreads ticks", () => {
    expect(indexAt(0.5, 11)).toBe(5);
    expect(indexAt(2, 11)).toBe(10);
    expect(ticks(11)).toEqual([0, 3, 5, 8, 10]);
    expect(ticks(1)).toEqual([0]);
    expect(ticks(0)).toEqual([]);
  });
});

describe("market rows", async () => {
  const { cryptoRow, quoteRow, rangePosition } = await import("./rows");
  it("maps quotes and crypto onto one row shape", () => {
    const q = quoteRow({
      instrument: { symbol: "BZ=F", name: "Brent", asset_class: "commodity", unit: "USD/bbl" },
      price: 97.44,
      previous_close: 106.6,
      change: -9.16,
      change_pct: -8.59,
      day_low: 96,
      day_high: 100,
      currency: "USD",
      as_of: "2026-09-27T18:00:00Z",
      history: [1, 2],
      source: "yahoo",
      delayed: true,
    });
    expect(q).toMatchObject({ group: "Energy", dayLow: 96, history: [1, 2] });
    expect(rangePosition(q)).toBe(36);
    const btc = cryptoRow({
      id: "bitcoin",
      symbol: "btc",
      name: "Bitcoin",
      price_usd: 110,
      change_24h_pct: 10,
      change_7d_pct: null,
      market_cap_usd: null,
      volume_24h_usd: null,
      updated_at: null,
      source: "coingecko",
    });
    expect(btc).toMatchObject({ symbol: "BTC-USD", group: "Crypto" });
    expect(btc.change).toBeCloseTo(10);
    expect(rangePosition(btc)).toBeNull();
  });
});
