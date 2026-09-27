/**
 * Human-readable popup rows. The API speaks SI; conversions to aviation and
 * nautical units happen here, for display only.
 */

const HIDDEN = new Set([
  "status",
  "title",
  "watch_kind",
  "watch_value",
  "watch_key",
  "heading_deg",
  "kinds",
]);

const LABELS: Record<string, string> = {
  altitude_m: "Altitude",
  altitude_km: "Altitude",
  velocity_ms: "Speed",
  speed_kms: "Speed",
  occurred_at: "Time",
  last_seen: "Last seen",
  at: "Computed at",
  elements_age_days: "Elements age",
  type_code: "Type",
  origin_country: "Country",
  num_articles: "Articles",
  num_sources: "Sources",
  ships_per_day: "Ships / day (7 d)",
  vs_last_year: "vs same week last year",
  vs_prior_90_days: "vs prior 90 days",
  reported_violence: "Violence",
  news_attention: "News",
  air_alerts: "Air alerts",
  internet_outages: "Outages",
  natural_hazards: "Hazards",
};

const numberFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });

function formatNumber(value: number): string {
  return numberFormat.format(value);
}

function humanise(key: string): string {
  const label = LABELS[key] ?? key.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function formatValue(key: string, value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") {
    switch (key) {
      case "altitude_m":
        return `${formatNumber(value)} m (${formatNumber(value / 0.3048)} ft)`;
      case "velocity_ms":
        return `${formatNumber(value)} m/s (${formatNumber(value / (1852 / 3600))} kt)`;
      case "altitude_km":
        return `${formatNumber(value)} km`;
      case "speed_kms":
        return `${formatNumber(value)} km/s`;
      case "severity":
        return `${Math.round(value * 100)} %`;
      case "elements_age_days":
        return `${formatNumber(value)} days`;
      default:
        return formatNumber(value);
    }
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime()))
      return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
  }
  return String(value);
}

export interface PopupRow {
  label: string;
  value: string;
  href?: string;
}

/** Rows for a feature's popup, in property order, skipping empty and internal ones. */
export function popupRows(properties: Record<string, unknown>): PopupRow[] {
  const rows: PopupRow[] = [];
  for (const [key, raw] of Object.entries(properties)) {
    if (HIDDEN.has(key)) continue;
    const value = formatValue(key, raw);
    if (value === null) continue;
    if (key === "url" || key === "source_url") {
      // Only http(s) links are ever rendered as links.
      if (/^https?:\/\//i.test(value))
        rows.push({ label: "Link", value: "open source", href: value });
      continue;
    }
    rows.push({ label: humanise(key), value });
  }
  return rows;
}
