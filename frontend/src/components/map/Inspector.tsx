"use client";

import { useState } from "react";
import { LiveMedia, type MediaKind } from "@/components/media/LiveMedia";
import { popupRows } from "@/features/map/format";
import type { Selection } from "@/features/map/MapCanvas";
import type { LayerUpdate } from "@/features/map/scheduler";
import { formatRelative } from "@/lib/time/relative";
import { UNVERIFIED_LAYERS } from "./LayersDrawer";
import { Swatch } from "./Swatch";

export interface InspectorActions {
  watched: boolean | null;
  onWatch(): void;
  tracked: boolean | null;
  onTrack(): void;
  /** null: not an aircraft. */
  cockpit?: boolean | null;
  onCockpit?(): void;
  onAsk(): void;
}

interface Props {
  selection: Selection;
  update: LayerUpdate | undefined;
  now: number;
  actions: InspectorActions;
  onClose(): void;
  /** Distance from the right edge (room for the assistant panel). */
  right?: number;
}

function coordinates(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(2)}°${ns} ${Math.abs(lon).toFixed(2)}°${ew}`;
}

/** Everything the feed says about one object — and nothing it does not ("—" stays "—"). */
export function Inspector({ selection, update, now, actions, onClose, right = 12 }: Props) {
  const [copied, setCopied] = useState(false);
  const { layer, properties } = selection;
  const unverified = UNVERIFIED_LAYERS.has(layer.id);
  const rows = popupRows(properties).filter((r) => r.label !== "Source");
  const coords = coordinates(selection.lat, selection.lon);
  const source = typeof properties.source === "string" ? properties.source : null;
  const media = typeof properties.media_url === "string" ? properties.media_url : null;

  const copy = () => {
    void navigator.clipboard?.writeText(coords).catch(() => {});
    setCopied(true);
  };

  return (
    <aside className="side-card inspector glass" aria-label="Inspector" style={{ right }}>
      <div className="card-head">
        <span className="inspector-kicker">
          <Swatch layer={layer} />
          {layer.label}
          {unverified && <span className="badge-unverified">Unverified</span>}
        </span>
        <button type="button" className="icon-btn" aria-label="Close inspector" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="card-body">
        <h2>{String(properties.title ?? "")}</h2>
        <p className="inspector-sub mono">{coords}</p>
        {media && (
          <LiveMedia
            key={media}
            kind={(properties.feed as MediaKind | undefined) ?? "image"}
            url={media}
            still={typeof properties.still_url === "string" ? properties.still_url : null}
            title={String(properties.title ?? "")}
          />
        )}
        <div className="inspector-actions">
          <button
            type="button"
            aria-pressed={actions.watched === true}
            disabled={actions.watched === null}
            onClick={actions.onWatch}
            title={actions.watched === null ? "Only aircraft and ships can be watched" : undefined}
          >
            <span className="glyph" aria-hidden="true">
              {actions.watched ? "★" : "☆"}
            </span>
            {actions.watched ? "Watching" : "Watch"}
          </button>
          <button
            type="button"
            aria-pressed={actions.tracked === true}
            disabled={actions.tracked === null}
            onClick={actions.onTrack}
            title={actions.tracked === null ? "No track for this object" : undefined}
          >
            <span className="glyph" aria-hidden="true">
              ⌇
            </span>
            {actions.tracked ? "Hide track" : "Show track"}
          </button>
          {actions.cockpit != null && (
            <button
              type="button"
              onClick={actions.onCockpit}
              title="Ride this aircraft on the 3D globe"
            >
              <span className="glyph" aria-hidden="true">
                ✈
              </span>
              Cockpit
            </button>
          )}
          <button type="button" onClick={actions.onAsk}>
            <span className="glyph" aria-hidden="true">
              ✦
            </span>
            Ask
          </button>
          <button type="button" onClick={copy}>
            <span className="glyph" aria-hidden="true">
              ⌖
            </span>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        {unverified && (
          <p className="note note-unverified">
            Coded automatically from press reports. Open the source articles before relying on this
            event.
          </p>
        )}
        {layer.note && <p className="note">{layer.note}</p>}
        <dl className="fields">
          {rows.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>
                {row.href ? (
                  <a href={row.href} target="_blank" rel="noopener noreferrer">
                    {row.value}
                  </a>
                ) : (
                  row.value
                )}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="card-foot">
        <span>{source ?? "—"}</span>
        <span>
          {update?.status === "ready"
            ? `updated ${formatRelative(new Date(update.loadedAt).toISOString(), now)}`
            : ""}
        </span>
      </div>
    </aside>
  );
}
