"use client";

import { useState } from "react";
import { isUnverifiedSource } from "@/features/assistant/chat";
import type { ApiClient } from "@/lib/api/client";
import type { PredictionReading } from "@/lib/api/types";

const STANCE: Record<PredictionReading["stance"], { label: string; cls: string }> = {
  leans_yes: { label: "Argus data leans yes", cls: "tag tag-warn" },
  leans_no: { label: "Argus data leans no", cls: "tag tag-ok" },
  no_conclusion: { label: "No conclusion", cls: "tag" },
};

/** "Analyse" under a prediction market: does Argus' own data lean one way? */
export function PredictionAnalysis({ api, marketId }: { api: ApiClient; marketId: string }) {
  const [reading, setReading] = useState<PredictionReading | null>(null);
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");

  const run = async () => {
    setState("busy");
    try {
      setReading(await api.analysePrediction(marketId));
      setState("idle");
    } catch {
      setState("failed");
    }
  };

  if (!reading) {
    return (
      <p className="hint">
        <button
          type="button"
          className="btn btn-s"
          disabled={state === "busy"}
          onClick={() => void run()}
        >
          {state === "busy" ? "Reading the feeds…" : "✦ Analyse with Argus data"}
        </button>
        {state === "failed" && <span className="notice-error"> The analysis failed.</span>}
      </p>
    );
  }
  const stance = STANCE[reading.stance];
  const a = reading.answer;
  return (
    <section className="ai-answer" aria-label="Analysis">
      <span className={stance.cls}>{stance.label}</span>
      <p className="ai-text" style={{ marginTop: 6 }}>
        {a.text}
      </p>
      {a.ungrounded.length > 0 && (
        <p className="note">▲ Figures not found in the data: {a.ungrounded.join(", ")}.</p>
      )}
      <ul className="chips">
        {a.sources.map((s) => (
          <li key={s}>
            <span className={`chip chip-small${isUnverifiedSource(s) ? " tag-unverified" : ""}`}>
              {s}
            </span>
          </li>
        ))}
      </ul>
      <p className="intel-footer">
        {a.model} · {a.steps.length} tool calls · the market price is not used as evidence
      </p>
    </section>
  );
}
