import { describe, expect, it } from "vitest";
import type { ChokepointTraffic, Quote } from "@/lib/api/types";
import {
  formatChange,
  formatPrice,
  formatSigned,
  formatUsd,
  quoteLabel,
  trafficStatus,
} from "./format";

describe("formatting", () => {
  it.each([
    [7743.41, "7\u202f743"],
    [97.44, "97.44"],
    [14.87, "14.87"],
    [1.14234, "1.1423"],
  ])("formatPrice(%s)", (value, text) => {
    expect(formatPrice(value)).toBe(text);
  });

  it("formats signed changes with a true minus", () => {
    expect(formatSigned(1.734, 2)).toBe("+1.73");
    expect(formatSigned(-0.02, 2)).toBe("\u22120.02");
    expect(formatSigned(0, 1)).toBe("0.0");
    expect(formatSigned(null, 2)).toBe("—");
  });

  it("formats changes with a direction glyph", () => {
    expect(formatChange(1.234)).toEqual({ text: "▲ 1.23 %", tone: "up" });
    expect(formatChange(-8.59)).toEqual({ text: "▼ 8.59 %", tone: "down" });
    expect(formatChange(0.001)).toEqual({ text: "0.00 %", tone: "flat" });
    expect(formatChange(null)).toEqual({ text: "—", tone: "flat" });
  });

  it("formats dollars compactly when large", () => {
    expect(formatUsd(84544)).toBe("$84\u202f544");
    expect(formatUsd(1_697_336_024_875)).toBe("$1.7T");
    expect(formatUsd(null)).toBe("—");
  });

  it("adds units except points", () => {
    const q = (unit: string | null) => ({ price: 97.44, instrument: { unit } }) as unknown as Quote;
    expect(quoteLabel(q("USD/bbl"))).toBe("97.44 USD/bbl");
    expect(quoteLabel(q("pts"))).toBe("97.44");
    expect(quoteLabel(q(null))).toBe("97.44");
    expect(quoteLabel({ price: 5.184, instrument: { unit: "%" } } as unknown as Quote)).toBe(
      "5.18 %",
    );
  });
});

describe("trafficStatus", () => {
  const c = (change: number | null, avg = 10) =>
    ({ change_vs_last_year_pct: change, last_7d_avg: avg }) as unknown as ChokepointTraffic;
  it.each([
    [c(-96.3, 3.1), "halted"],
    [c(-100, 0), "halted"],
    [c(-60), "severe"],
    [c(-30), "reduced"],
    [c(5), "normal"],
    [c(40), "busier"],
    [c(null), "unknown"],
  ])("%o -> %s", (item, status) => {
    expect(trafficStatus(item)).toBe(status);
  });
});
