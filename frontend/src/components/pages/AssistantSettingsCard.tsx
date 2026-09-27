"use client";

import { useEffect, useState } from "react";
import type { ApiClient } from "@/lib/api/client";
import type { AssistantSettings, AssistantTest, Usage } from "@/lib/api/types";

/** Anthropic models are the ones this project documents; any LiteLLM name works. */
const SUGGESTED = [
  "anthropic/claude-sonnet-5",
  "anthropic/claude-opus-5-5",
  "anthropic/claude-haiku-4-5-20251001",
];
const OLLAMA_DOCKER = "http://host.docker.internal:11434";

interface Props {
  api: ApiClient;
  onChanged(settings: AssistantSettings): void;
}

export function AssistantSettingsCard({ api, onChanged }: Props) {
  const [settings, setSettings] = useState<AssistantSettings | null>(null);
  const [model, setModel] = useState("");
  const [base, setBase] = useState("");
  const [embedding, setEmbedding] = useState("");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [key, setKey] = useState("");
  const [local, setLocal] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [test, setTest] = useState<AssistantTest | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const c = new AbortController();
    api.assistantSettings(c.signal).then(
      (s) => {
        setSettings(s);
        setModel(s.model ?? "");
        setEmbedding(s.embedding_model ?? "");
        setBase(s.api_base ?? "");
      },
      () => setStatus("Settings are unavailable."),
    );
    return () => c.abort();
  }, [api]);

  useEffect(() => {
    const c = new AbortController();
    api.usage(30, c.signal).then(setUsage, () => setUsage(null));
    return () => c.abort();
  }, [api]);

  // Models pulled on the Ollama server, when one is named.
  useEffect(() => {
    if (!/^https?:\/\/\S+$/.test(base)) {
      setLocal([]);
      return;
    }
    const c = new AbortController();
    const t = setTimeout(() => {
      api.localModels(base, c.signal).then(setLocal, () => setLocal([]));
    }, 400);
    return () => {
      clearTimeout(t);
      c.abort();
    };
  }, [api, base]);

  const save = async (removeKey = false) => {
    setBusy(true);
    setTest(null);
    try {
      const s = await api.saveAssistantSettings({
        model: model.trim() || null,
        api_base: base.trim() || null,
        embedding_model: embedding.trim() || null,
        // Omitted = keep the stored key; "" = remove it.
        ...(removeKey ? { api_key: "" } : key ? { api_key: key } : {}),
      });
      setSettings(s);
      setKey("");
      setStatus(s.model ? `Saved · ${s.model}` : "Assistant turned off");
      onChanged(s);
    } catch {
      setStatus("The server refused these settings (check the model name and URL).");
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    try {
      setTest(await api.testAssistant());
    } catch {
      setTest({ ok: false, model: null, elapsed_s: null, error: "No model is configured." });
    } finally {
      setBusy(false);
    }
  };

  const options = [...new Set([...local, ...SUGGESTED])];
  return (
    <section className="key-card" aria-labelledby="assistant-settings">
      <div className="card-title">
        <h3 id="assistant-settings">Assistant model</h3>
        {settings?.available ? (
          <span className="tag tag-ok">
            ● {settings.source === "app" ? "saved in the app" : "from .env"}
          </span>
        ) : (
          <span className="tag tag-warn">○ Off</span>
        )}
      </div>
      <p className="notice" style={{ color: "var(--text-2)" }}>
        Any model LiteLLM supports: <code>ollama/mistral</code> (local, nothing leaves the machine),{" "}
        <code>anthropic/claude-sonnet-5</code>, <code>openai/…</code>, <code>groq/…</code>,{" "}
        <code>openrouter/…</code>, <code>mistral/…</code>, <code>gemini/…</code>…
      </p>
      <form
        className="stack"
        style={{ gap: 10, marginTop: 12 }}
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label className="field">
          <span>Model</span>
          <input
            className="input input-wide mono"
            list="assistant-models"
            placeholder="provider/model, e.g. ollama/mistral"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <datalist id="assistant-models">
            {options.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </label>
        <label className="field">
          <span>API key</span>
          <input
            className="input input-wide mono"
            type="password"
            autoComplete="off"
            placeholder={
              settings?.key_set
                ? `stored (${settings.key_hint}) — type to replace`
                : "not needed for Ollama"
            }
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Base URL (optional)</span>
          <input
            className="input input-wide mono"
            placeholder={`for Ollama in Docker: ${OLLAMA_DOCKER}`}
            value={base}
            onChange={(e) => setBase(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Embedding model (optional, for search by meaning)</span>
          <input
            className="input input-wide mono"
            list="assistant-models"
            placeholder="e.g. ollama/nomic-embed-text — same key and base URL"
            value={embedding}
            onChange={(e) => setEmbedding(e.target.value)}
          />
        </label>
        {local.length > 0 && (
          <p className="hint">
            {local.length} local model{local.length > 1 ? "s" : ""} found: {local.join(", ")}
          </p>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Save
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || !settings?.available}
            onClick={() => void runTest()}
          >
            Test
          </button>
          {settings?.key_set && (
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy}
              onClick={() => void save(true)}
            >
              Remove key
            </button>
          )}
        </div>
        {status && (
          <p className="hint" aria-live="polite">
            {status}
          </p>
        )}
        {test && (
          <p className={`hint${test.ok ? "" : " bad"}`} aria-live="polite">
            {test.ok ? `● ${test.model} answered in ${test.elapsed_s} s` : `■ ${test.error}`}
          </p>
        )}
        {settings && settings.fallbacks.length > 0 && (
          <p className="hint">Fallbacks from .env: {settings.fallbacks.join(", ")}</p>
        )}
        {usage && (
          <p
            className="hint"
            title={usage.by_model.map((m) => `${m.model}: ${m.calls} calls`).join("\n")}
          >
            Last {usage.days} days: {usage.calls} model calls ·{" "}
            {(usage.input_tokens + usage.output_tokens).toLocaleString("en")} tokens · $
            {usage.cost_usd.toFixed(4)} estimated
            {usage.calls_without_cost > 0
              ? ` (+${usage.calls_without_cost} calls of unknown price)`
              : ""}
          </p>
        )}
        <p className="hint">
          The key is stored by the Argus server and never sent back to the browser. You can also set{" "}
          <code>ARGUS_LLM_MODEL</code>, <code>ARGUS_LLM_API_KEY</code> and{" "}
          <code>ARGUS_LLM_API_BASE</code> in <code>.env</code>.
        </p>
      </form>
      <details className="hint" style={{ marginTop: 10 }}>
        <summary>Use Argus from Claude Desktop or Claude Code (MCP)</summary>
        <p>
          Argus serves its data as read-only MCP tools at <code>http://localhost:8000/mcp</code>.
          With Claude Code:{" "}
          <code>claude mcp add --transport http argus http://localhost:8000/mcp</code>
        </p>
      </details>
    </section>
  );
}
