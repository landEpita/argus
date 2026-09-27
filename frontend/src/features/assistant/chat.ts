import { popupRows } from "@/features/map/format";
import type { Answer, AskInput } from "@/lib/api/types";

export type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; answer: Answer }
  | { role: "error"; text: string };

export const HISTORY_TURNS = 6;
export const QUESTION_MAX = 2000;

/** Earlier exchanges, as the API takes them: answers only, never the tool traces. */
export function historyOf(turns: readonly Turn[]): AskInput["history"] {
  const out: NonNullable<AskInput["history"]> = [];
  for (const t of turns) {
    if (t.role === "user") out.push({ role: "user", content: t.text });
    else if (t.role === "assistant") out.push({ role: "assistant", content: t.answer.text });
  }
  return out.slice(-HISTORY_TURNS);
}

/** Press-coded and state sources are shown dashed, like everywhere else. */
export function isUnverifiedSource(name: string): boolean {
  return /unverified|telegram|state media/i.test(name);
}

/** What is on screen, for "Ask about this": the inspector's own rows, capped. */
export function contextOf(
  kind: string,
  properties: Record<string, unknown>,
  lat: number,
  lon: number,
): NonNullable<AskInput["context"]> {
  const details: Record<string, string> = {};
  for (const row of popupRows(properties).slice(0, 12)) {
    if (!row.href) details[row.label] = row.value.slice(0, 120);
  }
  return {
    kind: kind.slice(0, 60),
    title: String(properties.title ?? "this object").slice(0, 200),
    lat,
    lon,
    details,
  };
}

export function answerMeta(a: Answer): string {
  const calls = a.steps.length;
  return `${a.model} · ${a.elapsed_s.toFixed(1)} s · ${calls} ${calls === 1 ? "tool call" : "tool calls"}`;
}
