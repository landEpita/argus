import type { Ownership, Story, StorySource } from "@/lib/api/types";

export const TIER_LABELS: Record<number, string> = {
  1: "Established newsroom",
  2: "Specialist / regional outlet",
  3: "State-controlled, no press freedom",
};

export const OWNERSHIP_LABELS: Record<Ownership, string> = {
  private: "privately owned",
  public: "public broadcaster (editorially independent)",
  state: "state-controlled",
  intergovernmental: "intergovernmental",
};

/** One line per source for the tooltip: "BBC News — tier 1, public broadcaster (…)". */
export function describeSource(source: StorySource): string {
  return `${source.name} — tier ${source.tier}: ${TIER_LABELS[source.tier] ?? "unrated"}, ${OWNERSHIP_LABELS[source.ownership]}`;
}

/** Stories reported by several outlets are more likely to be solid; say how many. */
export function coverageLabel(story: Story): string {
  const n = story.sources.length;
  return n === 1 ? "1 source" : `${n} sources`;
}

export const CHANNEL_PATTERN = /^[A-Za-z][A-Za-z0-9_]{4,31}$/;

/** Client-side mirror of the server's handle normalisation, for instant feedback. */
export function parseChannel(input: string): string | null {
  const handle = input
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/^t\.me\/(s\/)?/, "")
    .replace(/^@/, "")
    .replace(/\/+$/, "");
  return CHANNEL_PATTERN.test(handle) ? handle.toLowerCase() : null;
}

export const SUGGESTED_CHANNELS = ["osintdefender", "wartranslated", "intelslava"] as const;
