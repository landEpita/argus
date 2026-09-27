"use client";

import { useMemo } from "react";
import type { CountryDirectory } from "@/features/intel/countries";
import { PollingResource } from "@/features/intel/resource";
import { missingInputs } from "@/features/intel/signals";
import { useResource } from "@/features/intel/useResource";
import { corroborationLabel, type Situation, toSituation } from "@/features/map/situations";
import type { ApiClient } from "@/lib/api/client";
import type { ConvergenceCollection } from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";

interface Props {
  api: ApiClient;
  countries: CountryDirectory;
  focused: string | null;
  onFocus(situation: Situation): void;
}

function Segments({ s }: { s: Situation }) {
  const segs = [
    ...Array.from({ length: Math.min(3, s.corroborating) }, () => "seg-verified"),
    ...Array.from(
      { length: Math.min(3 - Math.min(3, s.corroborating), s.unverified) },
      () => "seg-unverified",
    ),
  ];
  while (segs.length < 3) segs.push("");
  return (
    <span className="segs" aria-hidden="true">
      {segs.map((c, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed three segments
        <span key={i} className={c} />
      ))}
    </span>
  );
}

export function SituationsList({ api, countries, focused, onFocus }: Props) {
  const resource = useMemo(
    () => new PollingResource<ConvergenceCollection>((s) => api.convergence(s), 300_000),
    [api],
  );
  const { data, error } = useResource(resource);
  const situations = useMemo(
    () => (data?.items ?? []).map((c, i) => toSituation(c, i + 1, (iso) => countries.name(iso))),
    [data, countries],
  );
  const missing = data ? missingInputs(data.inputs) : null;

  return (
    <div>
      {missing && <p className="notice notice-warn">{missing}</p>}
      {error != null && !data && <p className="notice notice-error">Unavailable right now.</p>}
      {data && situations.length === 0 && (
        <div className="empty">
          <strong>Nothing converging</strong>No area has two independent kinds of signal right now.
        </div>
      )}
      {situations.map((s) => (
        <article key={s.id} className="situation" aria-current={focused === s.id}>
          <div className="situation-head">
            <span className="situation-rank">{String(s.rank).padStart(2, "0")}</span>
            <h3>{s.title}</h3>
            <span className="situation-place">{s.place}</span>
          </div>
          <ul className="signal-chips">
            {s.signals.map((g) => (
              <li
                key={g.kind}
                className={`signal-chip${g.unverified ? " unverified" : ""}`}
                title={g.examples.join("\n")}
              >
                {g.label} <strong>{g.count}</strong>
              </li>
            ))}
          </ul>
          <div className={`corroboration${s.corroborating < 2 ? " weak" : ""}`}>
            <Segments s={s} />
            {corroborationLabel(s)}
          </div>
          <div className="situation-foot">
            <time dateTime={s.latest} title={formatUtc(s.latest)}>
              latest {formatRelative(s.latest)}
            </time>
            <button
              type="button"
              className={focused === s.id ? "btn btn-s" : "btn btn-s btn-primary"}
              onClick={() => onFocus(s)}
              aria-label={`Focus ${s.place}`}
            >
              {focused === s.id ? "In focus" : "Focus"}
            </button>
          </div>
        </article>
      ))}
      <p className="notice">
        A situation needs at least two kinds of signal in the same 2° cell. Figures are computed by
        Argus; press-coded reports never count as corroboration. A reason to look, not a conclusion.
      </p>
    </div>
  );
}
