"use client";

import type { Health } from "@/lib/api/types";

interface Props {
  health: Health | null;
  unreachable: boolean;
  onClick(): void;
}

/** ● Live, ▲ Degraded (a source is failing), ■ Offline (the API itself is unreachable). */
export function HealthPill({ health, unreachable, onClick }: Props) {
  const failing = health?.sources.filter((s) => s.status === "failing") ?? [];
  const [label, glyph, tone] = unreachable
    ? ["Offline", "■", "bad"]
    : failing.length
      ? ["Degraded", "▲", "warn"]
      : health
        ? ["Live", "●", "ok"]
        : ["Connecting", "○", "idle"];
  const title = unreachable
    ? "API unreachable"
    : failing.length
      ? failing.map((s) => `${s.source}: ${s.last_error ?? "failing"}`).join("\n")
      : "All sources healthy";
  return (
    <span role="status" aria-live="polite">
      <button type="button" className={`pill pill-${tone}`} title={title} onClick={onClick}>
        <span aria-hidden="true">{glyph}</span> {label}
        {failing.length > 0 && <span className="sr-only">: {failing.length} sources failing</span>}
      </button>
    </span>
  );
}
