import { describe, expect, it } from "vitest";
import type { AlertRule } from "@/lib/api/types";
import { describeRule, initialValues, paramsFrom, RULE_KINDS } from "./rules";

const rule = (kind: AlertRule["kind"], params: Record<string, unknown>, channels: string[] = []) =>
  ({
    id: "r",
    name: "n",
    kind,
    params,
    channels,
    enabled: true,
    created_at: "",
    last_fired_at: null,
  }) as AlertRule;

describe("alert rules", () => {
  it("turns form strings into typed params", () => {
    expect(initialValues("earthquake")).toEqual({ min_magnitude: "6", countries: "" });
    expect(paramsFrom("earthquake", { min_magnitude: "6.5", countries: "TW, jp ," })).toEqual({
      min_magnitude: 6.5,
      countries: ["TW", "jp"],
    });
    expect(paramsFrom("disaster_alert", { min_level: "orange", countries: "" })).toEqual({
      min_level: "orange",
      countries: [],
    });
    expect(paramsFrom("daily_digest", { hour_utc: "", frequency: "", weekday: "" })).toEqual({});
  });

  it("reads each rule as a sentence, with where it goes", () => {
    const channels = [{ id: "c1", name: "ops", kind: "discord" as const, hint: "discord.com" }];
    expect(
      describeRule(rule("earthquake", { min_magnitude: 6, countries: ["TW"] }, ["c1"]), channels),
    ).toBe("Earthquake ≥ M 6 in TW → ops");
    expect(describeRule(rule("keyword", { keywords: ["hormuz", "blockade"] }), channels)).toBe(
      "“hormuz”, “blockade” in the news → in-app only",
    );
    expect(describeRule(rule("ticker_move", { min_change_pct: 3, symbols: [] }), [])).toBe(
      "Any watched instrument moves more than 3 % → in-app only",
    );
    expect(RULE_KINDS.daily_digest.when({ hour_utc: 7 })).toBe("Every day after 07:00 UTC");
    expect(RULE_KINDS.daily_digest.when({ hour_utc: 8, frequency: "weekly", weekday: 0 })).toBe(
      "Every Monday after 08:00 UTC",
    );
    expect(
      paramsFrom("daily_digest", { frequency: "weekly", weekday: "4", hour_utc: "7" }),
    ).toEqual({
      frequency: "weekly",
      weekday: 4,
      hour_utc: 7,
    });
    expect(RULE_KINDS.convergence.when({ min_verified_kinds: 2 })).toBe(
      "2+ verified kinds of signal converge",
    );
  });
});
