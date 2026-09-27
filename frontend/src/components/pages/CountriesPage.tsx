"use client";

import { useEffect, useMemo, useState } from "react";
import { StoryItem } from "@/components/intel/StoryItem";
import { useFeed } from "@/components/shell/useFeed";
import type { CountryDirectory } from "@/features/intel/countries";
import { bucketHistory, describeSignal } from "@/features/intel/history";
import { COMPONENT_LABELS, missingInputs } from "@/features/intel/signals";
import type { ApiClient } from "@/lib/api/client";
import type { CountryDetail, CountrySignalCollection } from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";

interface Props {
  api: ApiClient;
  countries: CountryDirectory;
  iso2: string | null;
  followed: (iso2: string) => boolean;
  onSelect(iso2: string): void;
  onFollow(iso2: string, name: string): void;
  onOpenMap(iso2: string): void;
}

export function CountriesPage({
  api,
  countries,
  iso2,
  followed,
  onSelect,
  onFollow,
  onOpenMap,
}: Props) {
  const [query, setQuery] = useState("");
  const load = useMemo(() => (s: AbortSignal) => api.countrySignals(s), [api]);
  const { data, error } = useFeed<CountrySignalCollection>(load, 300_000);
  const q = query.trim().toLowerCase();
  const list = (data?.items ?? []).filter(
    (c) => !q || c.name.toLowerCase().includes(q) || c.iso2.toLowerCase() === q,
  );
  const selected = iso2 ?? data?.items[0]?.iso2 ?? null;
  const anyBaseline = data?.items.some((c) => c.has_baseline) ?? false;

  return (
    <main className="page" aria-label="Countries">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <h1>Countries</h1>
            <p>One page per country: what the feeds report, how the score is made, the news.</p>
          </div>
        </div>
        <div className="country-layout">
          <section className="card" aria-label="Country list">
            <div className="card-pad">
              <input
                className="input input-wide"
                placeholder="Filter countries"
                aria-label="Filter countries"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="list-button muted" style={{ padding: "0 16px 8px", fontSize: 12 }}>
              <span>Country</span>
              <span>Signal index</span>
            </div>
            {error != null && !data && (
              <p className="notice notice-error card-pad">The index is unavailable.</p>
            )}
            <ol className="country-list">
              {list.map((c) => (
                <li key={c.iso2}>
                  <button
                    type="button"
                    className="country-row"
                    aria-current={selected === c.iso2}
                    onClick={() => onSelect(c.iso2)}
                  >
                    <span className="code">{c.iso2}</span>
                    <span className="country-name">
                      {c.name}
                      {followed(c.iso2) && (
                        <span className="dim">
                          {" "}
                          <span aria-hidden="true">★</span>
                          <span className="sr-only">followed</span>
                        </span>
                      )}
                    </span>
                    <meter
                      className="sr-only"
                      value={c.score}
                      min={0}
                      max={100}
                      aria-label="Score"
                    />
                    <span className="num">{c.score.toFixed(0)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
          <div className="stack">
            <p className="notice">
              <strong>Country Signal Index</strong>: disruptive activity the feeds report now
              (0–100). It is not a measure of a country's stability.
              {data && !anyBaseline && (
                <span className="notice-warn">
                  {" "}
                  No baseline yet: scores become relative to each country's usual level after a day
                  of hourly snapshots.
                </span>
              )}
            </p>
            {selected ? (
              <CountryView
                api={api}
                iso2={selected}
                countries={countries}
                followed={followed(selected)}
                onFollow={onFollow}
                onOpenMap={onOpenMap}
                onSelect={onSelect}
              />
            ) : (
              data && <div className="empty">No country has a signal right now.</div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

interface ViewProps {
  api: ApiClient;
  iso2: string;
  countries: CountryDirectory;
  followed: boolean;
  onFollow(iso2: string, name: string): void;
  onOpenMap(iso2: string): void;
  onSelect(iso2: string): void;
}

function CountryView({ api, iso2, countries, followed, onFollow, onOpenMap, onSelect }: ViewProps) {
  const [detail, setDetail] = useState<CountryDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setFailed(false);
    api
      .countryDetail(iso2, controller.signal)
      .then(setDetail)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [api, iso2]);

  const now = useMemo(() => Date.now(), []);
  if (failed) return <p className="notice notice-error">Could not load this country.</p>;
  if (!detail) return <p className="notice">Loading…</p>;

  const signal = detail.signal;
  const score = signal?.score ?? 0;
  // The window follows the history there is: one day at first, up to seven.
  const oldest = Math.min(now, ...detail.history.map((p) => Date.parse(p.at)));
  const days = Math.min(7, Math.max(1, Math.ceil((now - oldest) / 86_400_000)));
  const bars = bucketHistory(detail.history, now, days, days === 1 ? 24 : 28);
  const first = detail.history[0]?.score;
  const delta = first === undefined ? null : score - first;
  const missing = missingInputs(detail.inputs);

  return (
    <>
      <section className="card card-pad" aria-label={detail.name}>
        <div className="card-title">
          <div>
            <span className="kicker mono">{detail.iso2}</span>
            <h2 style={{ fontSize: 26 }}>{detail.name}</h2>
          </div>
          <div className="page-meta">
            <button
              type="button"
              className={followed ? "btn btn-primary" : "btn"}
              aria-pressed={followed}
              onClick={() => onFollow(detail.iso2, detail.name)}
            >
              {followed ? "★ Following" : "☆ Follow"}
            </button>
            <button type="button" className="btn" onClick={() => onOpenMap(detail.iso2)}>
              Show on map
            </button>
            <button type="button" className="btn" disabled title="The assistant arrives in phase 5">
              Ask Argus
            </button>
          </div>
        </div>
        <div style={{ display: "flex", gap: 32, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <span className="kicker">Signal index</span>
            <div>
              <span style={{ fontSize: 52, fontWeight: 700, letterSpacing: "-0.03em" }}>
                {score.toFixed(0)}
              </span>
              <span className="muted"> / 100</span>
            </div>
            {delta !== null && (
              <span className={delta > 0 ? "down" : delta < 0 ? "up" : "muted"}>
                {delta > 0 ? "▲ +" : delta < 0 ? "▼ −" : ""}
                {Math.abs(delta).toFixed(0)}
                {delta === 0 ? "unchanged" : ""} over {detail.history.length} snapshots
              </span>
            )}
          </div>
          <figure style={{ flex: 1, minWidth: 280, margin: 0 }}>
            <div
              className="score-bars"
              role="img"
              aria-label={`Score over the last ${days === 1 ? "24 hours" : `${days} days`}`}
            >
              {bars.map((b) => (
                <span
                  key={b.start}
                  title={`${formatUtc(new Date(b.start).toISOString())} · ${b.score ?? "no snapshot"}`}
                  className={`bar${b.score === null ? "" : b.score >= 70 ? " hi" : b.score >= 40 ? " mid" : ""}`}
                  style={{
                    height: `${b.score === null ? 0 : Math.max(3, b.score)}%`,
                    opacity: b.score === null ? 0.3 : 1,
                  }}
                />
              ))}
            </div>
            <figcaption className="axis">
              <span>{days === 1 ? "24 h ago" : `${days} days ago`}</span>
              <span>
                {detail.history.length
                  ? `${detail.history.length} hourly snapshots`
                  : "No history yet: snapshots are taken hourly."}
              </span>
              <span>now</span>
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="summary" aria-label="Summary">
        <strong>Summary</strong>{" "}
        <span className="muted" style={{ fontSize: 12 }}>
          · composed by Argus from the figures below, no language model
        </span>
        <p style={{ margin: "6px 0 0" }}>{describeSignal(detail.name, signal, missing)}</p>
      </section>

      {signal && (
        <div
          className="grid-4"
          style={{ gridTemplateColumns: `repeat(${signal.components.length}, minmax(0, 1fr))` }}
        >
          {signal.components.map((c) => (
            <div key={c.component} className="tile" title={c.rule}>
              <span className="kicker">{COMPONENT_LABELS[c.component]}</span>
              <span
                className="v"
                style={
                  c.component === "reported_violence" ? { color: "var(--unverified)" } : undefined
                }
              >
                {c.points}
                <small className="muted" style={{ fontSize: 13 }}>
                  {" "}
                  / {c.max_points}
                </small>
              </span>
              <span className="u">
                input {c.raw}
                {c.mode === "relative" ? ` · usual ${c.baseline_mean}` : " · absolute"}
                {c.component === "reported_violence" ? " · unverified" : ""}
              </span>
            </div>
          ))}
        </div>
      )}

      <section className="card card-pad" aria-labelledby="country-news">
        <div className="card-title">
          <h2 id="country-news">Stories mentioning {detail.name}</h2>
          <span>last 24 h</span>
        </div>
        {detail.stories.length === 0 && <p className="notice">None.</p>}
        <ol className="story-list">
          {detail.stories.map((story) => (
            <StoryItem
              key={story.id}
              story={story}
              countries={countries}
              onFocusCountry={onSelect}
            />
          ))}
        </ol>
        {signal && (
          <p className="notice" title={formatUtc(signal.computed_at)}>
            Index computed {formatRelative(signal.computed_at)}.
          </p>
        )}
      </section>
    </>
  );
}
