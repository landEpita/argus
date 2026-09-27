"use client";

import type { AlertItem } from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";

const GLYPH: Record<AlertItem["severity"], string> = { critical: "■", warning: "▲", info: "●" };

/** One fired alert: severity glyph, title, where it came from, whether it was delivered. */
export function AlertRow({ alert, onOpen }: { alert: AlertItem; onOpen(alert: AlertItem): void }) {
  const failed = alert.deliveries.filter((d) => !d.ok && !d.held);
  const held = alert.deliveries.filter((d) => d.held);
  return (
    <button type="button" className="list-button alert-row" onClick={() => onOpen(alert)}>
      <span>
        <span className={`sev sev-${alert.severity}`} aria-hidden="true">
          {GLYPH[alert.severity]}
        </span>{" "}
        {!alert.read && <span className="sr-only">Unread: </span>}
        <strong className={alert.read ? "" : "unread"}>{alert.title}</strong>
        {alert.unverified && <span className="badge-unverified"> Unverified</span>}
        <span className="sub muted" style={{ display: "block", fontSize: 12 }}>
          {alert.rule_name} · {alert.source}
          {held.length > 0 && (
            <span className="dim">
              {" "}
              · held for quiet hours ({held.map((d) => d.channel_name).join(", ")})
            </span>
          )}
          {failed.length > 0 && (
            <span
              className="notice-warn"
              title={failed.map((d) => `${d.channel_name}: ${d.error}`).join("\n")}
            >
              {" "}
              · ▲ not delivered to {failed.map((d) => d.channel_name).join(", ")}
            </span>
          )}
        </span>
      </span>
      <time
        className="dim"
        dateTime={alert.at}
        title={formatUtc(alert.at)}
        style={{ fontSize: 12 }}
      >
        {formatRelative(alert.at)}
      </time>
    </button>
  );
}
