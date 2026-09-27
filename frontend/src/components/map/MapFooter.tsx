"use client";

import { useMemo } from "react";
import { binEvents, HISTOGRAM_HOURS } from "@/features/map/histogram";
import type { LayerRegistry } from "@/features/map/layers/registry";
import { isRasterData, type LayerFeatures } from "@/features/map/layers/types";
import type { LayerUpdate } from "@/features/map/scheduler";
import { UNVERIFIED_LAYERS } from "./LayersDrawer";
import { Swatch } from "./Swatch";

interface Props {
  registry: LayerRegistry;
  enabled: ReadonlySet<string>;
  states: Readonly<Record<string, LayerUpdate>>;
  now: number;
  left: number;
  right: number;
  onToggle(id: string): void;
  onOpenLayers(): void;
}

export function MapFooter(props: Props) {
  const { registry, enabled, states, now } = props;
  const loaded = useMemo(() => {
    const out = new Map<string, LayerFeatures>();
    for (const id of enabled) {
      const s = states[id];
      if (s?.status === "ready" && !isRasterData(s.data)) out.set(id, s.data);
    }
    return out;
  }, [enabled, states]);
  // Re-bin once a minute, not every second.
  const minute = Math.floor(now / 60_000);
  const bins = useMemo(
    () => binEvents(loaded, UNVERIFIED_LAYERS, minute * 60_000),
    [loaded, minute],
  );
  const total = bins.reduce((n, b) => n + b.verified + b.unverified, 0);
  const max = Math.max(1, ...bins.map((b) => b.verified + b.unverified));
  const active = registry.all().filter((l) => enabled.has(l.id));

  return (
    <div className="map-footer" style={{ left: props.left, right: props.right }}>
      <div className="layer-pills">
        <button type="button" className="layer-pill glass" onClick={props.onOpenLayers}>
          Layers · {enabled.size}
        </button>
        {active.map((layer) => {
          const s = states[layer.id];
          const count =
            s?.status === "ready" && !isRasterData(s.data)
              ? s.data.features.length.toLocaleString("en").replaceAll(",", " ")
              : s?.status === "error"
                ? "▲"
                : "";
          return (
            <button
              key={layer.id}
              type="button"
              className="layer-pill glass"
              title={`Hide ${layer.label}`}
              onClick={() => props.onToggle(layer.id)}
            >
              <Swatch layer={layer} />
              {layer.label}
              <span className="count">{count}</span>
            </button>
          );
        })}
      </div>
      <section
        className="histogram glass"
        aria-label={`Events in the last ${HISTOGRAM_HOURS} hours`}
      >
        <div className="histogram-title">
          <strong>Last {HISTOGRAM_HOURS} h</strong>
          <span>{total.toLocaleString("en")} events on screen</span>
        </div>
        <div className="histogram-bars">
          <ol>
            {bins.map((b) => {
              const at = new Date(b.start).toISOString().slice(11, 16);
              return (
                <li
                  key={b.start}
                  title={`${at} UTC · ${b.verified} verified, ${b.unverified} unverified`}
                >
                  <span
                    className="bar-verified"
                    style={{ height: `${(b.verified / max) * 100}%` }}
                  />
                  {b.unverified > 0 && (
                    <span
                      className="bar-unverified"
                      style={{ height: `${(b.unverified / max) * 100}%` }}
                    />
                  )}
                </li>
              );
            })}
          </ol>
          <div className="axis" aria-hidden="true">
            <span>−6 h</span>
            <span>−4 h</span>
            <span>−2 h</span>
            <span>now</span>
          </div>
        </div>
        <div className="legend">
          <span>
            <i className="i-verified" /> Verified
          </span>
          <span>
            <i className="i-unverified" /> Unverified
          </span>
        </div>
      </section>
    </div>
  );
}
