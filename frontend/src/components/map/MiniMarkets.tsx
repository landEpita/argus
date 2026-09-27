"use client";

import { useMemo } from "react";
import { PollingResource } from "@/features/intel/resource";
import { useResource } from "@/features/intel/useResource";
import { formatChange, quoteLabel } from "@/features/markets/format";
import type { ApiClient } from "@/lib/api/client";
import type { QuoteBoard } from "@/lib/api/types";

const SHOWN = ["BZ=F", "CL=F", "TTF=F", "GC=F", "EURUSD=X", "^GSPC", "^VIX"];

export function MiniMarkets({ api, onOpen }: { api: ApiClient; onOpen(): void }) {
  const resource = useMemo(
    () => new PollingResource<QuoteBoard>((s) => api.quotes(s), 60_000),
    [api],
  );
  const { data, error } = useResource(resource);
  const quotes = SHOWN.flatMap((s) => data?.items.filter((q) => q.instrument.symbol === s) ?? []);
  return (
    <div>
      {error != null && !data && <p className="notice notice-error">Quotes unavailable.</p>}
      <ul className="list">
        {quotes.map((q) => {
          const change = formatChange(q.change_pct);
          return (
            <li key={q.instrument.symbol} className="list-button">
              <span>{q.instrument.name}</span>
              <span className="num">
                {quoteLabel(q)} <span className={change.tone}>{change.text}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="notice">Delayed prices ({data?.items[0]?.source ?? "—"}).</p>
      <button type="button" className="btn btn-s" onClick={onOpen}>
        Open Markets ›
      </button>
    </div>
  );
}
