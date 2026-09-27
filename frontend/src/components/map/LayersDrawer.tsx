"use client";

import type { LayerRegistry } from "@/features/map/layers/registry";
import type { LayerGroup } from "@/features/map/layers/types";
import type { LayerUpdate } from "@/features/map/scheduler";
import { layerStatus } from "./layerStatus";
import { Swatch } from "./Swatch";

const GROUP_LABELS: Record<LayerGroup, string> = {
  movement: "Movement",
  space: "Space",
  events: "Events",
  infrastructure: "Infrastructure",
  analysis: "Analysis",
  imagery: "Weather & imagery",
};

/** Press-coded layers carry a warning wherever they are listed. */
export const UNVERIFIED_LAYERS: ReadonlySet<string> = new Set(["conflict"]);

interface Props {
  registry: LayerRegistry;
  enabled: ReadonlySet<string>;
  states: Readonly<Record<string, LayerUpdate>>;
  now: number;
  onToggle(id: string): void;
  onClose(): void;
  onKeys(): void;
}

export function LayersDrawer({ registry, enabled, states, now, onToggle, onClose, onKeys }: Props) {
  return (
    <aside className="side-card layers-drawer glass" aria-label="Layers">
      <div className="card-head">
        <div>
          <h2>Layers</h2>
          <p>{enabled.size} active</p>
        </div>
        <button type="button" className="icon-btn" aria-label="Close layers" onClick={onClose}>
          ‹
        </button>
      </div>
      <div className="card-body">
        {[...registry.byGroup()].map(([group, layers]) => {
          const on = layers.filter((l) => enabled.has(l.id)).length;
          return (
            <section key={group} className="layer-family">
              <h3>
                {GROUP_LABELS[group]}
                <span>{on ? `${on} on` : ""}</span>
              </h3>
              {layers.map((layer) => {
                const active = enabled.has(layer.id);
                const update = states[layer.id];
                const status = layerStatus(active, update, now);
                return (
                  <div key={layer.id}>
                    <button
                      type="button"
                      className="layer-row"
                      aria-pressed={active}
                      title={layer.note}
                      onClick={() => onToggle(layer.id)}
                    >
                      <Swatch layer={layer} />
                      <span className="layer-name">{layer.label}</span>
                      <span className="layer-count">{status.count}</span>
                      <span className="switch" aria-hidden="true" />
                      <span
                        className={`layer-status ${status.tone === "warn" ? "warn" : status.tone === "bad" ? "bad" : ""}`}
                      >
                        {status.text}
                      </span>
                    </button>
                    {active && UNVERIFIED_LAYERS.has(layer.id) && (
                      <p className="layer-note unverified note-inline">
                        Unverified — automated coding of press reports. Leads, not facts.
                      </p>
                    )}
                    {active && update?.status === "unavailable" && (
                      <button type="button" className="btn btn-s" onClick={onKeys}>
                        Add API key…
                      </button>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}
      </div>
    </aside>
  );
}
