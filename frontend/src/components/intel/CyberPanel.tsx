"use client";

import { useMemo } from "react";
import { PollingResource } from "@/features/intel/resource";
import { useResource } from "@/features/intel/useResource";
import type { ApiClient } from "@/lib/api/client";
import type { VulnerabilityCollection } from "@/lib/api/types";

export function CyberPanel({ api }: { api: ApiClient }) {
  const resource = useMemo(
    () =>
      new PollingResource<VulnerabilityCollection>(
        (signal) => api.exploited(30, signal),
        3_600_000,
      ),
    [api],
  );
  const { data, error } = useResource(resource);

  return (
    <div className="intel-panel">
      <p className="notice">
        Vulnerabilities confirmed as exploited in the wild, added to CISA's catalog in the last 30
        days. Internet outages are a map layer (Events).
      </p>
      {error != null && !data && (
        <p className="notice notice-error">The catalog is unavailable right now.</p>
      )}
      {data && data.items.length === 0 && <p className="notice">Nothing added in 30 days.</p>}
      <ol className="story-list">
        {data?.items.map((v) => (
          <li key={v.cve} className="story">
            <a href={v.url} target="_blank" rel="noopener noreferrer" className="story-title">
              {v.cve} — {v.vendor} {v.product}
            </a>
            <div className="story-meta">
              <span>added {v.date_added}</span>
              {v.used_in_ransomware === true && (
                <span className="tag tag-warn">Used by ransomware</span>
              )}
              {v.due_date && (
                <span title="Deadline for US federal agencies">patch by {v.due_date}</span>
              )}
            </div>
            {v.description && <p className="post-text">{v.description}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
