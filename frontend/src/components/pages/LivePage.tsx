"use client";

import { useEffect, useMemo, useState } from "react";
import { StreamPlayer } from "@/components/media/StreamPlayer";
import { useFeed } from "@/components/shell/useFeed";
import { loadWall, place, saveWall, WALL_SIZE } from "@/features/live/wall";
import type { ApiClient } from "@/lib/api/client";
import type { LiveChannel, Stream, Webcam } from "@/lib/api/types";

type Tab = "tv" | "webcams";

interface Entry {
  id: string;
  name: string;
  detail: string;
  streams: readonly Stream[];
  position?: { lat: number; lon: number } | null;
}

const LANGUAGE = new Intl.DisplayNames(["en"], { type: "language" });

function channelEntry(c: LiveChannel): Entry {
  const owner = c.ownership === "state" ? "state-owned" : c.ownership;
  const language = LANGUAGE.of(c.language) ?? c.language;
  return {
    id: c.id,
    name: c.name,
    detail: [c.country, language, owner].filter(Boolean).join(" · "),
    streams: c.streams,
  };
}

function webcamEntry(w: Webcam): Entry {
  const where = w.position
    ? `${w.position.lat.toFixed(2)}°, ${w.position.lon.toFixed(2)}°`
    : "from orbit";
  return { id: w.id, name: w.name, detail: where, streams: w.streams, position: w.position };
}

interface Props {
  api: ApiClient;
  tab: string | null;
  onTab(tab: Tab): void;
  onOpenMap(lat: number, lon: number): void;
}

/** A wall of four live players, filled from the TV channel or webcam list. */
export function LivePage({ api, tab: rawTab, onTab, onOpenMap }: Props) {
  const tab: Tab = rawTab === "webcams" ? "webcams" : "tv";
  const loadChannels = useMemo(() => (s: AbortSignal) => api.liveChannels(s), [api]);
  const loadWebcams = useMemo(() => (s: AbortSignal) => api.webcams(s), [api]);
  const channels = useFeed<LiveChannel[]>(loadChannels, 86_400_000);
  const webcams = useFeed<Webcam[]>(loadWebcams, 86_400_000);

  const entries = useMemo(
    () =>
      tab === "tv"
        ? (channels.data ?? []).map(channelEntry)
        : (webcams.data ?? []).map(webcamEntry),
    [tab, channels.data, webcams.data],
  );
  const byId = useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries]);
  const storageKey = `argus.live.${tab}`;
  const [wall, setWall] = useState<string[]>([]);
  const [slot, setSlot] = useState(0);

  useEffect(() => {
    setWall(
      entries.length
        ? loadWall(
            storageKey,
            entries.map((e) => e.id),
          )
        : [],
    );
    setSlot(0);
  }, [storageKey, entries]);

  const choose = (id: string) => {
    const next = place(wall, slot, id);
    setWall(next);
    saveWall(storageKey, next);
    setSlot((slot + 1) % WALL_SIZE);
  };
  const error = tab === "tv" ? channels.error : webcams.error;

  return (
    <main className="page" aria-label="Live">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <h1>Live</h1>
            <p>
              News channels and city webcams, played straight from the broadcaster. Argus does not
              check that a stream is on air; a stream that fails to load says so.
            </p>
          </div>
          <div role="tablist" aria-label="Live feeds" className="segmented">
            {(["tv", "webcams"] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => onTab(t)}
              >
                {t === "tv" ? "TV channels" : "Webcams"}
              </button>
            ))}
          </div>
        </div>
        {error != null && <p className="notice notice-error">The list could not be loaded.</p>}
        <div className="live-layout">
          <section className="live-wall" aria-label="Players">
            {wall.map((id, i) => {
              const entry = byId.get(id);
              if (!entry) return null;
              return (
                <article
                  key={id}
                  className={`card live-tile${i === slot ? " live-tile-active" : ""}`}
                  aria-label={entry.name}
                >
                  <div className="live-tile-head">
                    <button
                      type="button"
                      className="list-button"
                      aria-pressed={i === slot}
                      title="Pick a channel from the list to show it here"
                      onClick={() => setSlot(i)}
                    >
                      <strong>{entry.name}</strong>
                      <span className="dim">{entry.detail}</span>
                    </button>
                    {entry.position && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-s"
                        onClick={() =>
                          entry.position && onOpenMap(entry.position.lat, entry.position.lon)
                        }
                      >
                        Map
                      </button>
                    )}
                  </div>
                  <StreamPlayer title={entry.name} streams={entry.streams} />
                </article>
              );
            })}
          </section>
          <section className="card" aria-label={tab === "tv" ? "Channels" : "Webcams"}>
            <p className="card-pad dim" style={{ margin: 0 }}>
              Picks go to tile {slot + 1}.
            </p>
            <ul className="live-list">
              {entries.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    className="list-button"
                    aria-current={wall.includes(e.id) ? "true" : undefined}
                    onClick={() => choose(e.id)}
                  >
                    <span>{e.name}</span>
                    <span className="dim">{e.detail}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </main>
  );
}
