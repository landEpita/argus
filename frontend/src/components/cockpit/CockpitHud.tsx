"use client";

import { useEffect } from "react";
import type { CockpitState } from "@/features/map/cesium/renderer";

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;
const fmt = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });

function clock(relativeDeg: number): string {
  const hour = Math.round(((relativeDeg + 360) % 360) / 30) || 12;
  return `${hour} o'clock`;
}

/** Heads-up display over the cockpit view: our instruments, then traffic around us. */
export function CockpitHud({ state, onExit }: { state: CockpitState; onExit(): void }) {
  const { fix } = state;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onExit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onExit]);

  const heading = fix.headingDeg;
  return (
    <section className="hud" aria-label="Cockpit">
      <div className="hud-top">
        <strong className="mono">{fix.callsign}</strong>
        <span className={state.lost ? "notice-warn" : "dim"}>
          {state.lost
            ? "No longer in the feed · holding last position"
            : `Last report ${Math.round(state.reportAgeS)} s ago${state.extrapolated ? " · position extrapolated" : ""}`}
        </span>
        <button type="button" className="btn btn-s" onClick={onExit}>
          Exit cockpit (Esc)
        </button>
      </div>
      <div className="hud-heading mono">
        {heading === null
          ? "HDG —"
          : `HDG ${fmt.format(heading).padStart(3, "0")}° ${COMPASS[Math.round(heading / 45) % 8]}`}
      </div>
      <dl className="hud-tapes mono">
        <div>
          <dt>ALT</dt>
          <dd>
            {fix.altitudeM === null
              ? "—"
              : `${fmt.format(fix.altitudeM)} m · ${fmt.format(fix.altitudeM / 0.3048)} ft`}
          </dd>
        </div>
        <div>
          <dt>GS</dt>
          <dd>
            {fix.speedMs === null
              ? "—"
              : `${fmt.format(fix.speedMs * 3.6)} km/h · ${fmt.format(fix.speedMs / (1852 / 3600))} kt`}
          </dd>
        </div>
        <div>
          <dt>POS</dt>
          <dd>
            {fix.lat.toFixed(3)}°, {fix.lon.toFixed(3)}°
          </dd>
        </div>
      </dl>
      <section className="hud-traffic" aria-label="Traffic within 250 km">
        <h3>Traffic · 250 km</h3>
        {state.contacts.length === 0 ? (
          <p className="dim">No other aircraft on the map within 250 km.</p>
        ) : (
          <ol>
            {state.contacts.map((c) => (
              <li key={c.id} className="mono">
                <span>{c.callsign}</span>
                <span>{fmt.format(c.distanceKm)} km</span>
                <span>{clock(c.relativeDeg)}</span>
                <span>
                  {c.altitudeDeltaM === null
                    ? "alt —"
                    : `${c.altitudeDeltaM >= 0 ? "+" : "−"}${fmt.format(Math.abs(c.altitudeDeltaM))} m`}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}
