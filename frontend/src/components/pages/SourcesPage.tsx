"use client";

import { useMemo } from "react";
import { useFeed } from "@/components/shell/useFeed";
import {
  KEYS,
  keyConfigured,
  type SourceStatus,
  sourceRows,
  summarise,
} from "@/features/sources/catalogue";
import type { ApiClient } from "@/lib/api/client";
import type { AssistantSettings, Capabilities, Health } from "@/lib/api/types";
import { AssistantSettingsCard } from "./AssistantSettingsCard";

const STATUS: Record<SourceStatus, { label: string; glyph: string; tone: string }> = {
  ok: { label: "OK", glyph: "●", tone: "up" },
  down: { label: "Down", glyph: "■", tone: "down" },
  stale: { label: "Stale data", glyph: "▲", tone: "warn" },
  "needs-key": { label: "Needs key", glyph: "○", tone: "warn" },
  idle: { label: "Not called yet", glyph: "○", tone: "muted" },
};

function age(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

interface Props {
  api: ApiClient;
  health: Health | null;
  unreachable: boolean;
  onAssistantChanged(settings: AssistantSettings): void;
}

export function SourcesPage({ api, health, unreachable, onAssistantChanged }: Props) {
  const load = useMemo(() => (s: AbortSignal) => api.capabilities(s), [api]);
  const capabilities = useFeed<Capabilities>(load, 60_000);
  const rows = sourceRows(health, capabilities.data);
  const counts = summarise(rows);

  return (
    <main className="page" aria-label="Sources">
      <div className="page-inner page-narrow">
        <div className="page-head">
          <div>
            <h1>Sources</h1>
            <p>Every feed Argus reads, when it last succeeded and what it powers.</p>
          </div>
          <div className="page-meta">
            <span className="pill pill-ok">● {counts.ok} OK</span>
            <span className={counts.down ? "pill pill-bad" : "pill pill-idle"}>
              ■ {counts.down} down
            </span>
            <span className={counts.stale ? "pill pill-warn" : "pill pill-idle"}>
              ▲ {counts.stale} stale
            </span>
            <span className={counts["needs-key"] ? "pill pill-warn" : "pill pill-idle"}>
              ○ {counts["needs-key"]} need key
            </span>
          </div>
        </div>
        {unreachable && (
          <p className="notice notice-error">
            ■ The Argus API is unreachable; showing the last known state.
          </p>
        )}
        <section className="card" aria-label="Source health">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Powers</th>
                <th scope="col">Status</th>
                <th scope="col">Last success</th>
                <th scope="col">Refresh</th>
                <th scope="col">Last error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const s = STATUS[r.status];
                return (
                  <tr key={r.id}>
                    <th scope="row" style={{ fontWeight: 500, color: "var(--text)" }}>
                      {r.name}
                      {r.members > 1 && <span className="sub">{r.members} feeds</span>}
                    </th>
                    <td className="muted">{r.powers}</td>
                    <td className={s.tone}>
                      <span aria-hidden="true">{s.glyph}</span> {s.label}
                    </td>
                    <td>{age(r.lastSuccessAgeS)}</td>
                    <td className="muted">{r.refresh}</td>
                    <td
                      className="mono muted"
                      title={r.lastError ?? undefined}
                      style={{
                        maxWidth: 280,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {r.lastError ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && <div className="empty">No source has reported yet.</div>}
        </section>
        <p className="notice" style={{ marginTop: 8 }}>
          “Not called yet” means nobody has asked for that data since the server started: sources
          are only called when a layer or panel needs them.
        </p>

        <div className="page-head" style={{ marginTop: 32 }}>
          <div>
            <h2 style={{ fontSize: 22 }}>Settings & API keys</h2>
            <p>
              The assistant's model, and free keys that unlock more layers. Keys stay on the server,
              never in the browser.
            </p>
          </div>
        </div>
        <div className="grid-3">
          <AssistantSettingsCard api={api} onChanged={onAssistantChanged} />
          {KEYS.map((k) => {
            const configured = keyConfigured(k, capabilities.data);
            const missing = configured === false && !k.optional;
            return (
              <article key={k.setting} className={`key-card${missing ? " missing" : ""}`}>
                <div className="card-title">
                  <h3>{k.name}</h3>
                  {configured === null ? (
                    <span className="tag">…</span>
                  ) : k.optional ? (
                    <span className="tag">optional</span>
                  ) : configured ? (
                    <span className="tag tag-ok">● Active</span>
                  ) : (
                    <span className="tag tag-warn">○ Missing</span>
                  )}
                </div>
                <p className="notice" style={{ color: "var(--text-2)" }}>
                  {k.unlocks}
                </p>
                <p className="hint">
                  {k.how}:{" "}
                  <a href={k.url} target="_blank" rel="noopener noreferrer">
                    {new URL(k.url).host}
                  </a>
                </p>
                <p className="hint">
                  Set <code>{k.setting}</code> in <code>.env</code>, then restart the backend.
                </p>
              </article>
            );
          })}
        </div>
      </div>
    </main>
  );
}
