"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import type { CountryDirectory } from "@/features/intel/countries";
import { parseChannel, SUGGESTED_CHANNELS } from "@/features/intel/present";
import { PollingResource } from "@/features/intel/resource";
import { useResource } from "@/features/intel/useResource";
import { isCapabilityDisabled } from "@/features/map/scheduler";
import type { ApiClient } from "@/lib/api/client";
import type { TelegramCollection } from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";

interface Props {
  api: ApiClient;
  channels: readonly string[];
  onChannelsChange(channels: string[]): void;
  countries: CountryDirectory;
  onFocusCountry(iso2: string): void;
}

const EMPTY: TelegramCollection = { count: 0, items: [], channels: [] };

export function TelegramPanel({
  api,
  channels,
  onChannelsChange,
  countries,
  onFocusCountry,
}: Props) {
  const [draft, setDraft] = useState("");
  const [invalid, setInvalid] = useState(false);
  const resource = useMemo(
    () => new PollingResource<TelegramCollection>(async () => EMPTY, 60_000),
    [],
  );
  useEffect(() => {
    resource.setLoader((signal) =>
      channels.length ? api.telegram(channels, signal) : Promise.resolve(EMPTY),
    );
  }, [api, resource, channels]);
  const { data, error } = useResource(resource);

  const add = (raw: string) => {
    const handle = parseChannel(raw);
    if (!handle) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setDraft("");
    if (!channels.includes(handle)) onChannelsChange([...channels, handle]);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    add(draft);
  };
  const failing = new Map(
    (data?.channels ?? []).filter((c) => c.error).map((c) => [c.channel, c.error]),
  );

  if (error && isCapabilityDisabled(error)) {
    return (
      <p className="notice">Telegram is switched off on this server (ARGUS_TELEGRAM_ENABLED).</p>
    );
  }

  return (
    <div className="intel-panel">
      <form className="intel-toolbar" onSubmit={onSubmit}>
        <input
          type="text"
          placeholder="Add a public channel (@name or t.me link)"
          aria-label="Add a Telegram channel"
          aria-invalid={invalid}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="chip">
          Add
        </button>
      </form>
      {invalid && <p className="notice notice-error">Not a public channel name.</p>}

      <div className="chips">
        {channels.map((c) => (
          <span
            key={c}
            className={`chip chip-small ${failing.has(c) ? "chip-error" : ""}`}
            title={failing.get(c) ?? undefined}
          >
            @{c}
            <button
              type="button"
              aria-label={`Remove @${c}`}
              onClick={() => onChannelsChange(channels.filter((x) => x !== c))}
            >
              ×
            </button>
          </span>
        ))}
      </div>

      {channels.length === 0 && (
        <div className="notice">
          <p>
            Follow public OSINT channels. Posts are unverified claims, often from one side of a
            conflict.
          </p>
          <p>
            Try:{" "}
            {SUGGESTED_CHANNELS.map((c) => (
              <button key={c} type="button" className="chip chip-small" onClick={() => add(c)}>
                @{c}
              </button>
            ))}
          </p>
        </div>
      )}

      <ol className="story-list">
        {data?.items.map((post) => (
          <li key={post.id} className="story">
            <div className="story-meta">
              <strong>{post.channel_title ?? `@${post.channel}`}</strong>
              <time dateTime={post.published_at} title={formatUtc(post.published_at)}>
                {formatRelative(post.published_at)}
              </time>
              <span
                className="tag tag-unverified"
                title="Telegram posts are claims, not verified reports"
              >
                Unverified
              </span>
              {post.has_media && (
                <span className="tag" title="Has photo or video">
                  Media
                </span>
              )}
            </div>
            {post.text && <p className="post-text">{post.text}</p>}
            <div className="story-meta">
              <a href={post.url} target="_blank" rel="noopener noreferrer">
                Open on Telegram
              </a>
              {post.views && <span>{post.views} views</span>}
              {post.countries.slice(0, 3).map((code) => (
                <button
                  key={code}
                  type="button"
                  className="chip chip-small"
                  onClick={() => onFocusCountry(code)}
                >
                  {countries.name(code)}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
