import type { InputStatus, SignalComponent } from "@/lib/api/types";

export const COMPONENT_LABELS: Record<SignalComponent, string> = {
  reported_violence: "Reported violence",
  news_attention: "News attention",
  air_alerts: "Air-raid alerts",
  internet_outages: "Internet outages",
  natural_hazards: "Natural hazards",
};

/** "Computed without: news, air-alerts" — or null when every input answered. */
export function missingInputs(inputs: readonly InputStatus[]): string | null {
  const missing = inputs.filter((i) => !i.ok).map((i) => i.name.replace(/^events:/, ""));
  return missing.length ? `Computed without: ${missing.join(", ")}` : null;
}
