"use client";

import { useEffect, useRef, useState } from "react";
import {
  answerMeta,
  historyOf,
  isUnverifiedSource,
  QUESTION_MAX,
  type Turn,
} from "@/features/assistant/chat";
import {
  canSpeak,
  type Recognizer,
  recognizerCtor,
  speakable,
  transcriptOf,
} from "@/features/assistant/speech";
import { type ApiClient, ApiError } from "@/lib/api/client";
import type { Answer, AskInput, MapFocus } from "@/lib/api/types";

export interface Question {
  text: string;
  context?: AskInput["context"];
  /** Bumps so the same question can be asked twice. */
  id: number;
}

interface Props {
  api: ApiClient;
  question: Question | null;
  onClose(): void;
  onSettings(): void;
  onFocus(focus: MapFocus): void;
}

function reason(error: unknown): string {
  if (error instanceof ApiError) {
    const body = (error.body ?? {}) as { error?: string; message?: string };
    if (body.error === "capability_disabled") return "No model is configured.";
    if (body.error === "upstream_unavailable") return "The model did not answer (see Sources).";
    return body.message ?? `HTTP ${error.status}`;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

function AnswerView({ answer, onFocus }: { answer: Answer; onFocus(focus: MapFocus): void }) {
  return (
    <div className="ai-answer">
      {answer.steps.length > 0 && (
        <ol className="ai-steps" aria-label="Steps">
          {answer.steps.map((s, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: steps are ordered and immutable
            <li key={i} className={s.ok ? "" : "warn"}>
              <span aria-hidden="true">{s.ok ? "✓" : "○"}</span> read {s.tool}
              {Object.keys(s.args).length > 0 && (
                <span className="mono dim"> {JSON.stringify(s.args).slice(0, 80)}</span>
              )}{" "}
              · {s.summary}
            </li>
          ))}
        </ol>
      )}
      <p className="ai-text">{answer.text}</p>
      {!answer.conclusive && <p className="tag">No conclusion — the data does not settle it</p>}
      {answer.ungrounded.length > 0 && (
        <p className="note">
          ▲ These figures do not appear in the data Argus read: {answer.ungrounded.join(", ")}.
          Treat them as unverified.
        </p>
      )}
      {!answer.structured && (
        <p className="note">▲ The model did not follow the protocol; this is its raw reply.</p>
      )}
      {answer.sources.length > 0 && (
        <ul className="chips" aria-label="Sources read">
          {answer.sources.map((s) => (
            <li key={s}>
              <span className={`chip chip-small${isUnverifiedSource(s) ? " tag-unverified" : ""}`}>
                {s}
              </span>
            </li>
          ))}
        </ul>
      )}
      {answer.focus && (
        <button
          type="button"
          className="btn btn-s"
          onClick={() => answer.focus && onFocus(answer.focus)}
          title="From the places and layers the assistant read, not from its words"
        >
          ⌖ Show on map
          {answer.focus.layers.length > 0 ? ` · ${answer.focus.layers.join(", ")}` : ""}
        </button>
      )}
      <p className="intel-footer">{answerMeta(answer)}</p>
    </div>
  );
}

/** Questions answered from Argus' own data, with the steps and sources shown. */
export function AssistantPanel({ api, question, onClose, onSettings, onFocus }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [listening, setListening] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const recognizer = useRef<Recognizer | null>(null);
  const speech = typeof window === "undefined" ? undefined : (window as never);
  const Dictation = recognizerCtor(speech);
  const speaks = canSpeak(speech);

  const listen = () => {
    if (!Dictation) return;
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const r = new Dictation();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => setDraft(transcriptOf(e));
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recognizer.current = r;
    setListening(true);
    r.start();
  };
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);

  const send = async (text: string, context?: AskInput["context"]) => {
    const q = text.trim().slice(0, QUESTION_MAX);
    if (!q || thinking) return;
    const history = historyOf(turns);
    setTurns((t) => [...t, { role: "user", text: q }]);
    setDraft("");
    setThinking(true);
    controller.current = new AbortController();
    try {
      const answer = await api.ask({ question: q, context, history }, controller.current.signal);
      setTurns((t) => [...t, { role: "assistant", answer }]);
      if (readAloud && speaks) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(speakable(answer.text));
        utterance.lang = navigator.language || "en-US";
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) {
      if (!controller.current.signal.aborted)
        setTurns((t) => [...t, { role: "error", text: reason(error) }]);
    } finally {
      setThinking(false);
    }
  };

  // A question asked from elsewhere (inspector, palette).
  // biome-ignore lint/correctness/useExhaustiveDependencies: only a new question id triggers
  useEffect(() => {
    if (question) void send(question.text, question.context);
  }, [question?.id]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll on new turns
  useEffect(() => {
    // Braces matter: recent browsers return a Promise from scrollIntoView.
    end.current?.scrollIntoView({ block: "end" });
  }, [turns.length, thinking]);
  useEffect(
    () => () => {
      controller.current?.abort();
      recognizer.current?.stop();
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    },
    [],
  );

  return (
    <aside className="side-card assistant glass" aria-label="Assistant">
      <div className="card-head">
        <div>
          <h2>Ask Argus</h2>
          <p>Answers from Argus' data only, with its sources</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            className="icon-btn"
            aria-label="Model settings"
            onClick={onSettings}
          >
            ⚙
          </button>
          <button type="button" className="icon-btn" aria-label="Close assistant" onClick={onClose}>
            ×
          </button>
        </div>
      </div>
      <div className="card-body" aria-live="polite">
        {turns.length === 0 && (
          <div className="empty">
            <strong>Ask about what Argus shows</strong>
            “What is happening in the Red Sea?”, “How is oil doing?”, “Why is Ukraine's score
            high?”. The assistant reads the feeds, then answers — or says it cannot conclude.
          </div>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: an append-only conversation
            <p key={i} className="ai-user">
              {t.text}
            </p>
          ) : t.role === "assistant" ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: an append-only conversation
            <AnswerView key={i} answer={t.answer} onFocus={onFocus} />
          ) : (
            // biome-ignore lint/suspicious/noArrayIndexKey: an append-only conversation
            <p key={i} className="notice notice-error">
              ■ {t.text}
            </p>
          ),
        )}
        {thinking && <p className="notice">Reading the feeds…</p>}
        <div ref={end} />
      </div>
      <form
        className="ai-input"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <input
          className="input input-wide"
          aria-label="Question"
          placeholder="Ask about the map, a country, a market…"
          value={draft}
          maxLength={QUESTION_MAX}
          onChange={(e) => setDraft(e.target.value)}
        />
        {Dictation && (
          <button
            type="button"
            className="btn"
            aria-pressed={listening}
            aria-label={listening ? "Stop dictation" : "Dictate the question"}
            title="Uses your browser's speech recognition (some browsers send audio to their vendor)"
            onClick={listen}
          >
            {listening ? "■" : "🎙"}
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={thinking || !draft.trim()}>
          Ask
        </button>
      </form>
      {speaks && (
        <label className="ai-voice">
          <input
            type="checkbox"
            checked={readAloud}
            onChange={(e) => {
              setReadAloud(e.target.checked);
              if (!e.target.checked) window.speechSynthesis.cancel();
            }}
          />{" "}
          Read answers aloud
        </label>
      )}
    </aside>
  );
}
