import { describe, expect, it } from "vitest";
import type { Answer } from "@/lib/api/types";
import { answerMeta, contextOf, historyOf, isUnverifiedSource, type Turn } from "./chat";

const answer: Answer = {
  text: "Brent is down 8.59 %.",
  conclusive: true,
  steps: [{ tool: "quotes", args: {}, ok: true, summary: "22 items" }],
  sources: ["Yahoo Finance (delayed)"],
  ungrounded: [],
  provider: "llm",
  model: "ollama/mistral",
  elapsed_s: 3.14,
  structured: true,
  focus: null,
  stance: null,
};

describe("assistant chat", () => {
  it("keeps questions and answers, not errors or traces, for follow-ups", () => {
    const turns: Turn[] = [
      { role: "user", text: "oil?" },
      { role: "assistant", answer },
      { role: "error", text: "timeout" },
      { role: "user", text: "and gas?" },
    ];
    expect(historyOf(turns)).toEqual([
      { role: "user", content: "oil?" },
      { role: "assistant", content: "Brent is down 8.59 %." },
      { role: "user", content: "and gas?" },
    ]);
    const many = Array.from({ length: 20 }, (_, i) => ({ role: "user", text: String(i) }) as Turn);
    expect(historyOf(many)).toHaveLength(6);
  });

  it("marks press-coded and social sources", () => {
    expect(isUnverifiedSource("GDELT (unverified)")).toBe(true);
    expect(isUnverifiedSource("Telegram")).toBe(true);
    expect(isUnverifiedSource("USGS")).toBe(false);
  });

  it("describes what is on screen from the inspector rows", () => {
    const ctx = contextOf(
      "Live flights",
      { title: "SWR8LR", altitude_m: 10000, url: "https://x" },
      46.2,
      9.8,
    );
    expect(ctx).toEqual({
      kind: "Live flights",
      title: "SWR8LR",
      lat: 46.2,
      lon: 9.8,
      details: { Altitude: "10,000 m (32,808.4 ft)" },
    });
  });

  it("summarises how the answer was made", () => {
    expect(answerMeta(answer)).toBe("ollama/mistral · 3.1 s · 1 tool call");
  });
});
