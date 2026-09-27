"use client";

import { useMemo } from "react";
import { useFeed } from "@/components/shell/useFeed";
import type { ApiClient } from "@/lib/api/client";
import type { AlertFeed, AlertItem } from "@/lib/api/types";
import { AlertRow } from "./AlertRow";

/** The alerts tab of the map's left panel. */
export function AlertsFeed({
  api,
  onOpen,
  onManage,
}: {
  api: ApiClient;
  onOpen(alert: AlertItem): void;
  onManage(): void;
}) {
  const load = useMemo(() => (s: AbortSignal) => api.alerts(false, s), [api]);
  const { data, error } = useFeed<AlertFeed>(load, 60_000);
  return (
    <div>
      {error != null && !data && <p className="notice notice-error">Alerts are unavailable.</p>}
      {data?.items.length === 0 && (
        <div className="empty">
          <strong>No alert yet</strong>Rules you create in Watch fire here — and on your channels.
        </div>
      )}
      <ul className="list">
        {data?.items.map((a) => (
          <li key={a.id}>
            <AlertRow alert={a} onOpen={onOpen} />
          </li>
        ))}
      </ul>
      <button type="button" className="btn btn-s" onClick={onManage}>
        Manage rules ›
      </button>
    </div>
  );
}
