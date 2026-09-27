"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Segmented } from "@/components/shell/Segmented";
import type { CountryDirectory } from "@/features/intel/countries";
import { formatChange, quoteLabel } from "@/features/markets/format";
import { normaliseWatch, WATCH_KIND_LABELS, WATCH_PLACEHOLDERS } from "@/features/watch/normalise";
import type { ApiClient } from "@/lib/api/client";
import type {
  CountrySignalCollection,
  QuoteBoard,
  WatchItem,
  WatchKind,
  Watchlist,
} from "@/lib/api/types";

/** Where a watched aircraft or ship is right now, if a map layer has it in view. */
export interface Presence {
  lat: number;
  lon: number;
  detail: string;
}

interface Props {
  api: ApiClient;
  countries: CountryDirectory;
  listId: string | null;
  presence(kind: WatchKind, value: string): Presence | null;
  onSelectList(id: string): void;
  /** Called after any change, so the map can recolour watched objects. */
  onChanged(): void;
  onOpenMap(lat: number, lon: number): void;
  onOpenAsset(symbol: string): void;
  onOpenCountry(iso2: string): void;
}

const KINDS: WatchKind[] = ["aircraft", "vessel", "ticker", "country", "keyword"];

interface Status {
  glyph: string;
  tone: "up" | "warn" | "muted";
  text: string;
  context: string;
  action?: { label: string; run(): void };
}

export function WatchPage(props: Props) {
  const { api, countries } = props;
  const [lists, setLists] = useState<Watchlist[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [kind, setKind] = useState<WatchKind>("aircraft");
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<QuoteBoard | null>(null);
  const [signals, setSignals] = useState<CountrySignalCollection | null>(null);
  const [mentions, setMentions] = useState<Record<string, number | null>>({});

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setLists(await api.watchlists(signal));
        setFailed(null);
      } catch {
        if (!signal?.aborted) setFailed("Watchlists are unavailable right now.");
      }
    },
    [api],
  );

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    api.quotes(controller.signal).then(setQuotes, () => {});
    api.countrySignals(controller.signal).then(setSignals, () => {});
    return () => controller.abort();
  }, [api, reload]);

  const current = lists?.find((l) => l.id === props.listId) ?? lists?.[0] ?? null;

  // Keyword mentions: stories of the last 24 h whose text matches.
  useEffect(() => {
    const controller = new AbortController();
    for (const item of current?.items ?? []) {
      if (item.kind !== "keyword" || item.value in mentions) continue;
      api.news({ q: item.value, sinceHours: 24, limit: 100 }, controller.signal).then(
        (r) => setMentions((m) => ({ ...m, [item.value]: r.count })),
        () => setMentions((m) => ({ ...m, [item.value]: null })),
      );
    }
    return () => controller.abort();
  }, [api, current, mentions]);

  const save = async (list: Watchlist, items: WatchItem[]) => {
    try {
      await api.replaceWatchlist(list.id, { name: list.name, items });
      await reload();
      props.onChanged();
    } catch {
      setHint("The server refused the change.");
    }
  };

  const normalised = normaliseWatch(kind, value);
  const add = async () => {
    if (!current) return;
    if (!normalised.ok) return setHint(normalised.error);
    if (current.items.some((i) => i.kind === kind && i.value === normalised.value)) {
      return setHint(`${normalised.value} is already in this list.`);
    }
    await save(current, [
      ...current.items,
      { kind, value: normalised.value, label: label.trim() || null },
    ]);
    setValue("");
    setLabel("");
    setHint(null);
  };

  const createList = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      const list = await api.createWatchlist({ name, items: [] });
      setNewName("");
      await reload();
      props.onSelectList(list.id);
    } catch {
      setFailed(`Could not create “${name}” (names must be unique).`);
    }
  };

  const quoteOf = useMemo(
    () => new Map((quotes?.items ?? []).map((q) => [q.instrument.symbol, q])),
    [quotes],
  );
  const scoreOf = useMemo(
    () => new Map((signals?.items ?? []).map((c) => [c.iso2, c.score])),
    [signals],
  );

  const status = (item: WatchItem): Status => {
    switch (item.kind) {
      case "aircraft":
      case "vessel": {
        const p = props.presence(item.kind, item.value);
        return p
          ? {
              glyph: "●",
              tone: "up",
              text: "On the map now",
              context: p.detail,
              action: { label: "Map", run: () => props.onOpenMap(p.lat, p.lon) },
            }
          : {
              glyph: "○",
              tone: "muted",
              text: "Not in the current view",
              context: "Pan the map or widen the view to look for it",
            };
      }
      case "ticker": {
        const q = quoteOf.get(item.value);
        const change = formatChange(q?.change_pct);
        return {
          glyph: q ? (change.tone === "down" ? "▼" : "▲") : "○",
          tone: q ? (change.tone === "down" ? "warn" : "up") : "muted",
          text: q ? `${quoteLabel(q)} · ${change.text}` : "Not on the quote board",
          context: q ? "delayed" : "the chart can still load it",
          action: { label: "Chart", run: () => props.onOpenAsset(item.value) },
        };
      }
      case "country": {
        const score = scoreOf.get(item.value);
        return {
          glyph: score ? "▲" : "●",
          tone: score && score >= 40 ? "warn" : "muted",
          text: score === undefined ? "No signal right now" : `Signal index ${score.toFixed(0)}`,
          context: countries.name(item.value),
          action: { label: "Profile", run: () => props.onOpenCountry(item.value) },
        };
      }
      default: {
        const n = mentions[item.value];
        return {
          glyph: n ? "●" : "○",
          tone: "muted",
          text:
            n === undefined
              ? "Counting…"
              : n === null
                ? "News search unavailable"
                : `${n} ${n === 1 ? "story" : "stories"} · 24 h`,
          context: "matching news stories",
        };
      }
    }
  };

  return (
    <main className="page" aria-label="Watch">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <h1>Watch</h1>
            <p>What you follow, and what it is doing now.</p>
          </div>
          <span className="muted">{lists ? `${lists.length} / 50 lists` : ""}</span>
        </div>
        {failed && <p className="notice notice-error">{failed}</p>}
        <div className="watch-layout">
          <section className="card card-pad lists" aria-label="Lists">
            <span className="kicker">Lists</span>
            <ul className="list" style={{ margin: "6px 0 10px" }}>
              {lists?.map((l) => (
                <li key={l.id} style={{ padding: 0, border: 0 }}>
                  <button
                    type="button"
                    aria-current={current?.id === l.id}
                    onClick={() => props.onSelectList(l.id)}
                  >
                    {l.name}
                    <span className="n">{l.items.length}</span>
                  </button>
                </li>
              ))}
            </ul>
            {lists?.length === 0 && (
              <p className="notice">
                No list yet. ☆ Watch an aircraft or a ship on the map, or create one.
              </p>
            )}
            <div style={{ display: "flex", gap: 6 }}>
              <input
                className="input"
                style={{ flex: 1, minWidth: 0 }}
                placeholder="New list…"
                aria-label="New list name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void createList();
                }}
              />
              <button
                type="button"
                className="btn"
                aria-label="Create list"
                onClick={() => void createList()}
              >
                +
              </button>
            </div>
          </section>

          <section className="card" aria-label={current?.name ?? "List"}>
            {current ? (
              <>
                <div className="card-pad card-title">
                  <div>
                    <h2>{current.name}</h2>
                    <span>{current.items.length} of 500 items</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-s"
                    onClick={() => {
                      void navigator.clipboard
                        ?.writeText(JSON.stringify(current.items, null, 2))
                        .catch(() => {});
                    }}
                  >
                    Copy as JSON
                  </button>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Item</th>
                      <th scope="col">Status</th>
                      <th scope="col">Context</th>
                      <th scope="col">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.items.map((item) => {
                      const s = status(item);
                      return (
                        <tr key={`${item.kind}:${item.value}`}>
                          <td>
                            {item.label ?? <span className="dim">No label</span>}
                            <span className="sub mono">
                              {item.value} · {WATCH_KIND_LABELS[item.kind]}
                            </span>
                          </td>
                          <td className={s.tone}>
                            <span aria-hidden="true">{s.glyph}</span> {s.text}
                          </td>
                          <td className="muted">{s.context}</td>
                          <td className="num">
                            {s.action && (
                              <button type="button" className="btn btn-s" onClick={s.action.run}>
                                {s.action.label}
                              </button>
                            )}{" "}
                            <button
                              type="button"
                              className="btn btn-s btn-ghost"
                              aria-label={`Remove ${item.value}`}
                              onClick={() =>
                                void save(
                                  current,
                                  current.items.filter(
                                    (i) => !(i.kind === item.kind && i.value === item.value),
                                  ),
                                )
                              }
                            >
                              ×
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {current.items.length === 0 && (
                  <div className="empty">
                    <strong>This list is empty</strong>Add an item below, or use ☆ Watch on the map.
                  </div>
                )}
                <div className="card-pad" style={{ borderTop: "0.5px solid var(--hair)" }}>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    <span className="muted">Add</span>
                    <Segmented small label="Item type">
                      {KINDS.map((k) => (
                        <button
                          key={k}
                          type="button"
                          aria-pressed={kind === k}
                          onClick={() => {
                            setKind(k);
                            setHint(null);
                          }}
                        >
                          {WATCH_KIND_LABELS[k]}
                        </button>
                      ))}
                    </Segmented>
                    <input
                      className="input mono"
                      style={{ flex: 1, minWidth: 160 }}
                      aria-label="Value"
                      aria-invalid={Boolean(value.trim()) && !normalised.ok}
                      placeholder={WATCH_PLACEHOLDERS[kind]}
                      value={value}
                      onChange={(e) => {
                        setValue(e.target.value);
                        setHint(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void add();
                      }}
                    />
                    <input
                      className="input"
                      style={{ width: 140 }}
                      aria-label="Label"
                      placeholder="Label"
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                    />
                    <button type="button" className="btn btn-primary" onClick={() => void add()}>
                      Add
                    </button>
                  </div>
                  <p
                    className={`hint${hint || (value.trim() && !normalised.ok) ? " bad" : ""}`}
                    aria-live="polite"
                  >
                    {hint ??
                      (!value.trim()
                        ? "Inputs are cleaned automatically: “3C6444” becomes “3c6444”."
                        : normalised.ok
                          ? normalised.value !== value.trim()
                            ? `Will be saved as ${normalised.value}`
                            : "Looks good — press Enter to add"
                          : normalised.error)}
                  </p>
                </div>
              </>
            ) : (
              lists && <div className="empty">Create a list to start.</div>
            )}
          </section>

          <section className="card card-pad" aria-labelledby="watch-rules">
            <div className="card-title">
              <h2 id="watch-rules">Rules & activity</h2>
              <span className="soon">phase 6</span>
            </div>
            <p className="notice">
              Alert rules — “a watched aircraft appears”, “earthquake above M 6”, “a ticker moves
              more than 3 %” — and their delivery (in-app, browser, e-mail, Telegram, webhook)
              arrive in phase 6. Until then, statuses here are what the feeds show right now;
              nothing runs in the background.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
