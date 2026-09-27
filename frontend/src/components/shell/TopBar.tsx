"use client";

import { SPACE_LABELS, SPACES, type Space } from "@/features/shell/space";
import type { Health } from "@/lib/api/types";
import { HealthPill } from "./HealthPill";
import { useNow } from "./useNow";

interface Props {
  space: Space;
  onSpace(space: Space): void;
  onSearch(): void;
  health: Health | null;
  unreachable: boolean;
  askAvailable: boolean;
  onAsk(): void;
  unread: number;
  onAlerts(): void;
}

function UtcClock() {
  const now = new Date(useNow());
  return (
    <time className="clock" dateTime={now.toISOString()}>
      {now.toISOString().slice(11, 19)} <small>UTC</small>
    </time>
  );
}

export function TopBar({
  space,
  onSpace,
  onSearch,
  health,
  unreachable,
  askAvailable,
  onAsk,
  unread,
  onAlerts,
}: Props) {
  return (
    <header className="topbar glass">
      <div className="topbar-left">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Argus
        </span>
        <button type="button" className="search-trigger" onClick={onSearch}>
          <span className="search-glyph" aria-hidden="true" />
          <span className="search-text">Search or run a command…</span>
          <kbd>⌘K</kbd>
        </button>
      </div>
      <nav aria-label="Spaces" className="segmented">
        {SPACES.map((s) => (
          <button
            key={s}
            type="button"
            aria-current={space === s ? "page" : undefined}
            onClick={() => onSpace(s)}
          >
            {SPACE_LABELS[s]}
          </button>
        ))}
      </nav>
      <div className="topbar-right">
        <HealthPill health={health} unreachable={unreachable} onClick={() => onSpace("sources")} />
        <UtcClock />
        <button type="button" className="btn btn-ghost alerts-button" onClick={onAlerts}>
          Alerts
          {unread > 0 && (
            <>
              <span className="count-badge" aria-hidden="true">
                {unread > 99 ? "99+" : unread}
              </span>
              <span className="sr-only">{unread} unread</span>
            </>
          )}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onAsk}
          title={askAvailable ? undefined : "Choose a model first (Sources → Assistant model)"}
        >
          Ask Argus
        </button>
      </div>
    </header>
  );
}
