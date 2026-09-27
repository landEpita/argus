import type { AlertChannel, AlertRule, ChannelKind, RuleKind } from "@/lib/api/types";

/** A form field of a rule kind; values are strings in the form, typed when sent. */
export interface Field {
  name: string;
  label: string;
  type: "number" | "list" | "select";
  placeholder?: string;
  options?: readonly string[];
  initial: string;
  /** Lists: how items are written ("TW, JP"). */
  help?: string;
}

export interface KindInfo {
  label: string;
  /** "When …" phrase for the rule sentence. */
  when: (p: Record<string, unknown>) => string;
  fields: readonly Field[];
}

const countries: Field = {
  name: "countries",
  label: "Countries (optional)",
  type: "list",
  placeholder: "TW, JP — empty: anywhere",
  initial: "",
};

const inCountries = (p: Record<string, unknown>) => {
  const list = (p.countries as string[] | undefined) ?? [];
  return list.length ? ` in ${list.join(", ")}` : "";
};

export const RULE_KINDS: Record<RuleKind, KindInfo> = {
  earthquake: {
    label: "Earthquake",
    when: (p) => `Earthquake ≥ M ${p.min_magnitude ?? 6}${inCountries(p)}`,
    fields: [
      { name: "min_magnitude", label: "Minimum magnitude", type: "number", initial: "6" },
      countries,
    ],
  },
  disaster_alert: {
    label: "Disaster alert",
    when: (p) =>
      `${p.min_level === "orange" ? "Orange or red" : "Red"} disaster alert${inCountries(p)}`,
    fields: [
      {
        name: "min_level",
        label: "Level",
        type: "select",
        options: ["red", "orange"],
        initial: "red",
      },
      countries,
    ],
  },
  keyword: {
    label: "Keyword in the news",
    when: (p) => `“${((p.keywords as string[] | undefined) ?? []).join("”, “")}” in the news`,
    fields: [
      {
        name: "keywords",
        label: "Keywords",
        type: "list",
        placeholder: "hormuz, blockade",
        initial: "",
      },
      { name: "min_outlets", label: "Minimum outlets", type: "number", initial: "1" },
    ],
  },
  ticker_move: {
    label: "Price move",
    when: (p) => {
      const symbols = (p.symbols as string[] | undefined) ?? [];
      return `${symbols.length ? symbols.join(", ") : "Any watched instrument"} moves more than ${p.min_change_pct ?? 3} %`;
    },
    fields: [
      { name: "min_change_pct", label: "Minimum change (%)", type: "number", initial: "3" },
      {
        name: "symbols",
        label: "Symbols (optional)",
        type: "list",
        placeholder: "BZ=F, ^GSPC — empty: the watch set",
        initial: "",
      },
    ],
  },
  country_score: {
    label: "Country signal index",
    when: (p) => `Signal index ≥ ${p.min_score ?? 60}${inCountries(p)}`,
    fields: [
      { name: "min_score", label: "Minimum score", type: "number", initial: "60" },
      countries,
    ],
  },
  convergence: {
    label: "Converging signals",
    when: (p) => `${p.min_verified_kinds ?? 2}+ verified kinds of signal converge${inCountries(p)}`,
    fields: [
      {
        name: "min_verified_kinds",
        label: "Verified kinds",
        type: "number",
        initial: "2",
      },
      countries,
    ],
  },
  watched_aircraft: {
    label: "Aircraft is flying",
    when: (p) => `${((p.icao24 as string[] | undefined) ?? []).join(", ")} seen flying`,
    fields: [
      {
        name: "icao24",
        label: "ICAO 24-bit addresses",
        type: "list",
        placeholder: "3c6444, ae01ce",
        initial: "",
      },
    ],
  },
  daily_digest: {
    label: "Daily digest",
    when: (p) => `Every day after ${String(p.hour_utc ?? 7).padStart(2, "0")}:00 UTC`,
    fields: [{ name: "hour_utc", label: "Hour (UTC)", type: "number", initial: "7" }],
  },
};

export const CHANNEL_FIELDS: Record<
  ChannelKind,
  { name: string; label: string; secret: boolean }[]
> = {
  webhook: [{ name: "url", label: "URL (receives the alert as JSON)", secret: true }],
  discord: [{ name: "url", label: "Discord webhook URL", secret: true }],
  telegram: [
    { name: "bot_token", label: "Bot token (from @BotFather)", secret: true },
    { name: "chat_id", label: "Chat id", secret: false },
  ],
  email: [{ name: "to", label: "Address", secret: false }],
};

export function initialValues(kind: RuleKind): Record<string, string> {
  return Object.fromEntries(RULE_KINDS[kind].fields.map((f) => [f.name, f.initial]));
}

/** Form strings → the API's params: numbers parsed, lists split on commas. */
export function paramsFrom(
  kind: RuleKind,
  values: Record<string, string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of RULE_KINDS[kind].fields) {
    const raw = (values[f.name] ?? "").trim();
    if (f.type === "number") {
      if (raw !== "") out[f.name] = Number(raw);
    } else if (f.type === "list") {
      out[f.name] = raw
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    } else if (raw) {
      out[f.name] = raw;
    }
  }
  return out;
}

/** "Earthquake ≥ M 6 in TW → ops, phone" */
export function describeRule(rule: AlertRule, channels: readonly AlertChannel[]): string {
  const names = rule.channels
    .map((id) => channels.find((c) => c.id === id)?.name)
    .filter((n): n is string => Boolean(n));
  const to = names.length ? names.join(", ") : "in-app only";
  return `${RULE_KINDS[rule.kind].when(rule.params)} → ${to}`;
}
