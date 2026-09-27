"use client";

import { useEffect, useMemo, useState } from "react";
import { Segmented } from "@/components/shell/Segmented";
import { CHART_H, CHART_W, chartGeometry, indexAt, ticks } from "@/features/markets/chart";
import { formatChange, formatPrice, formatSigned, priceDigits } from "@/features/markets/format";
import type { MarketRow } from "@/features/markets/rows";
import type { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/client";
import type { AssetDetail, HistoryRange } from "@/lib/api/types";

const RANGES: { id: HistoryRange; label: string; span: string }[] = [
  { id: "1mo", label: "1M", span: "the month" },
  { id: "3mo", label: "3M", span: "3 months" },
  { id: "6mo", label: "6M", span: "6 months" },
  { id: "1y", label: "1Y", span: "the year" },
  { id: "5y", label: "5Y", span: "5 years" },
];

interface Props {
  api: ApiClient;
  symbol: string;
  row: MarketRow | undefined;
}

function shortDate(day: string, range: HistoryRange): string {
  const d = new Date(`${day}T00:00:00Z`);
  const opts: Intl.DateTimeFormatOptions =
    range === "5y" || range === "1y"
      ? { month: "short", year: "2-digit", timeZone: "UTC" }
      : { day: "numeric", month: "short", timeZone: "UTC" };
  return d.toLocaleDateString("en-GB", opts);
}

/** Price chart and technical reading of one instrument. */
export function AssetPanel({ api, symbol, row }: Props) {
  const [range, setRange] = useState<HistoryRange>("3mo");
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    api
      .asset(symbol, range, controller.signal)
      .then((d) => {
        setDetail(d);
        setHover(null);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setDetail(null);
        setError(
          e instanceof ApiError && e.status === 404
            ? `No price history for ${symbol}.`
            : "Price history is unavailable right now.",
        );
      });
    return () => controller.abort();
  }, [api, symbol, range]);

  const candles = detail?.instrument.symbol === symbol ? detail.candles : [];
  const closes = useMemo(() => candles.map((c) => c.close), [candles]);
  const geometry = useMemo(() => (closes.length ? chartGeometry(closes) : null), [closes]);
  const t = detail?.technicals ?? null;
  const last = candles.at(-1);
  const first = candles[0];
  const price = row?.price ?? last?.close ?? null;
  const digits = price === null ? 2 : priceDigits(price);
  const change = formatChange(row?.changePct);
  const rangePct = first && last ? ((last.close - first.close) / first.close) * 100 : null;
  const rangeChange = formatChange(rangePct);
  const levels = (t?.levels ?? []).filter(
    (l) => geometry && l.price >= geometry.min && l.price <= geometry.max,
  );
  const nearest = (kind: "support" | "resistance") =>
    t?.levels
      .filter((l) => l.kind === kind)
      .sort((a, b) => Math.abs(a.distance_pct) - Math.abs(b.distance_pct))[0];
  const support = nearest("support");
  const resistance = nearest("resistance");
  const hovered = hover !== null ? candles[hover] : undefined;
  const span = RANGES.find((r) => r.id === range)?.span ?? "";
  // The table's curated name first (e.g. "Bitcoin", not Yahoo's "BTC-USD").
  const name =
    row?.name ?? (detail?.instrument.symbol === symbol ? detail.instrument.name : symbol);
  const unit = row?.unit ?? detail?.instrument.unit ?? detail?.currency ?? "";

  const stats: [string, string][] = [
    ["Last open", last ? formatPrice(last.open, digits) : "—"],
    [
      "Prev. close",
      row?.change != null && price !== null ? formatPrice(price - row.change, digits) : "—",
    ],
    [
      "Range high",
      candles.length ? formatPrice(Math.max(...candles.map((c) => c.high)), digits) : "—",
    ],
    [
      "Range low",
      candles.length ? formatPrice(Math.min(...candles.map((c) => c.low)), digits) : "—",
    ],
    ["Support", support ? `${formatPrice(support.price, digits)} (${support.touches}×)` : "—"],
    [
      "Resistance",
      resistance ? `${formatPrice(resistance.price, digits)} (${resistance.touches}×)` : "—",
    ],
    ["50-day avg", t?.sma_50 != null ? formatPrice(t.sma_50, digits) : "—"],
    ["200-day avg", t?.sma_200 != null ? formatPrice(t.sma_200, digits) : "—"],
    ["RSI 14", t?.rsi_14 != null ? t.rsi_14.toFixed(0) : "—"],
    ["Sessions read", t ? String(t.sessions) : "—"],
  ];
  const pos52 =
    t && price !== null && t.high_52w > t.low_52w
      ? Math.min(100, Math.max(0, ((price - t.low_52w) / (t.high_52w - t.low_52w)) * 100))
      : null;

  return (
    <section className="card card-pad sticky" aria-label={`${name} chart`}>
      <div className="card-title">
        <div>
          <span className="kicker">
            <span className="mono">{symbol}</span>
            {row ? ` · ${row.group}` : ""}
            {detail?.exchange ? ` · ${detail.exchange}` : ""}
          </span>
          <h2 style={{ fontSize: 22 }}>{name}</h2>
        </div>
        <div style={{ textAlign: "right" }}>
          <span className="big">
            {price === null ? "—" : formatPrice(price, digits)}{" "}
            <small className="muted" style={{ fontSize: 13 }}>
              {unit}
            </small>
          </span>
          <div className={change.tone}>
            {row?.change != null ? formatSigned(row.change, digits) : ""} {change.text}
          </div>
        </div>
      </div>
      <div className="page-meta" style={{ justifyContent: "space-between" }}>
        <Segmented small label="Chart range">
          {RANGES.map((r) => (
            <button
              key={r.id}
              type="button"
              aria-pressed={range === r.id}
              onClick={() => setRange(r.id)}
            >
              {r.label}
            </button>
          ))}
        </Segmented>
        {rangePct !== null && (
          <span className={rangeChange.tone}>
            {rangeChange.text} over {span}
          </span>
        )}
      </div>
      {error && <p className="notice notice-error">{error}</p>}
      {geometry && (
        <div className="chart">
          {/* biome-ignore lint/a11y/noStaticElementInteractions: pointer read-out only; the figures below carry the same data. */}
          <div
            className="plot"
            onMouseMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              setHover(indexAt((e.clientX - r.left) / r.width, candles.length));
            }}
            onMouseLeave={() => setHover(null)}
          >
            {geometry.grid.map((v) => (
              <div key={v} className="gridline" style={{ top: `${geometry.yPercent(v)}%` }}>
                <span>{formatPrice(v, Math.min(digits, 2))}</span>
              </div>
            ))}
            {levels.map((l) => (
              <div
                key={`${l.kind}-${l.price}`}
                className={`levelline ${l.kind}`}
                style={{ top: `${geometry.yPercent(l.price)}%` }}
                title={`${l.kind} ${formatPrice(l.price, digits)} · touched ${l.touches}×, last ${l.last_touch}`}
              />
            ))}
            <svg
              viewBox={`0 0 ${CHART_W} ${CHART_H}`}
              preserveAspectRatio="none"
              role="img"
              aria-label={`${name}, daily closes over ${span}`}
            >
              <defs>
                <linearGradient id="argusArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#F58A3D" stopOpacity=".28" />
                  <stop offset="100%" stopColor="#F58A3D" stopOpacity="0" />
                </linearGradient>
              </defs>
              <polygon points={geometry.area} fill="url(#argusArea)" />
              <polyline
                points={geometry.line}
                fill="none"
                stroke="#F58A3D"
                strokeWidth="2"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            {hovered && hover !== null && (
              <>
                <span
                  className="hover-dot"
                  style={{
                    left: `${(hover / Math.max(1, candles.length - 1)) * 100}%`,
                    top: `${geometry.yPercent(hovered.close)}%`,
                  }}
                />
                <div
                  className="tooltip"
                  style={
                    hover > candles.length * 0.6
                      ? { right: `${100 - (hover / Math.max(1, candles.length - 1)) * 100 + 2}%` }
                      : { left: `${(hover / Math.max(1, candles.length - 1)) * 100 + 2}%` }
                  }
                >
                  {formatPrice(hovered.close, digits)} {unit}
                  <span>
                    {hovered.day} · H {formatPrice(hovered.high, digits)} · L{" "}
                    {formatPrice(hovered.low, digits)}
                  </span>
                </div>
              </>
            )}
          </div>
          <div className="xaxis" aria-hidden="true">
            {ticks(candles.length).map((i) => (
              <span key={i}>{candles[i] ? shortDate(candles[i].day, range) : ""}</span>
            ))}
          </div>
        </div>
      )}
      <dl className="stats">
        {stats.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {t && (
        <div className="range52">
          <div className="row">
            <span>52-week range</span>
            <span>
              {formatPrice(t.low_52w, digits)} – {formatPrice(t.high_52w, digits)}
            </span>
          </div>
          <div className="track">
            {pos52 !== null && <span className="knob" style={{ left: `${pos52}%` }} />}
          </div>
        </div>
      )}
      {t && (
        <ul className="method">
          {t.method.map((m) => (
            <li key={m}>{m}</li>
          ))}
          <li>Descriptive, not a forecast. Daily bars from {detail?.source ?? "—"}, delayed.</li>
        </ul>
      )}
    </section>
  );
}
