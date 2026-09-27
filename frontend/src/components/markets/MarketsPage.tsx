"use client";

import { useCallback, useMemo, useState } from "react";
import { errorReason } from "@/components/map/layerStatus";
import { Segmented } from "@/components/shell/Segmented";
import { useFeed } from "@/components/shell/useFeed";
import { useNow } from "@/components/shell/useNow";
import {
  formatChange,
  formatPrice,
  formatSigned,
  formatUsd,
  priceDigits,
  TRAFFIC_LABELS,
  trafficStatus,
} from "@/features/markets/format";
import { byGroup, MARKET_GROUPS, type MarketGroup } from "@/features/markets/groups";
import { cryptoRow, type MarketRow, quoteRow, rangePosition } from "@/features/markets/rows";
import { EXCHANGES, formatDuration, sessionState } from "@/features/markets/sessions";
import type { ApiClient } from "@/lib/api/client";
import type {
  CalendarEvent,
  ChokepointTraffic,
  CryptoAsset,
  EnergyBoard,
  FundingBoard,
  LiquidationBoard,
  MarketNote,
  PredictionMarket,
  QuoteBoard,
  SentimentIndex,
  YieldCurve,
} from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";
import { AssetPanel } from "./AssetPanel";
import { PredictionAnalysis } from "./PredictionReadingView";

const STRIP = ["^GSPC", "^STOXX", "^N225", "BZ=F", "GC=F", "EURUSD=X", "^TNX", "BTC-USD"];
const DEFAULT_ASSET = "BZ=F";

interface Props {
  api: ApiClient;
  symbol: string | null;
  onSymbol(symbol: string): void;
  onFocusPoint(lat: number, lon: number, layer?: string): void;
  /** A model is configured: prediction markets can be analysed. */
  canAnalyse: boolean;
}

function Unavailable({ what, error }: { what: string; error: unknown }) {
  const reason = errorReason({ layerId: what, status: "error", error });
  return (
    <p className="notice notice-error" title={reason}>
      {what} unavailable{reason ? ` — ${reason}` : ""}.
    </p>
  );
}

function Spark({ values, tone }: { values: readonly number[]; tone: string }) {
  if (values.length < 2) return <span className="dim">—</span>;
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * 100).toFixed(1)},${(20 - ((v - min) / span) * 18).toFixed(1)}`,
    )
    .join(" ");
  const color = tone === "up" ? "#7FB069" : tone === "down" ? "#E5484D" : "#9aa0ac";
  return (
    <svg className="spark" viewBox="0 0 100 22" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.4"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Sessions() {
  const now = new Date(useNow(30_000));
  return (
    <>
      {EXCHANGES.map((e) => {
        const s = sessionState(e, now);
        return (
          <span key={e.name} className={`session${s.open ? " open" : ""}`}>
            <i aria-hidden="true" />
            <strong>{e.name}</strong>
            {s.open ? "open" : "closed"} · {s.open ? "closes" : "opens"} in{" "}
            {formatDuration(s.minutesUntilChange)}
          </span>
        );
      })}
    </>
  );
}

export function MarketsPage({ api, symbol, onSymbol, onFocusPoint, canAnalyse }: Props) {
  const [group, setGroup] = useState<MarketGroup | "All">("All");
  const selected = symbol ?? DEFAULT_ASSET;

  const loaders = useMemo(
    () => ({
      quotes: (s: AbortSignal) => api.quotes(s),
      crypto: (s: AbortSignal) => api.crypto(10, s),
      funding: (s: AbortSignal) => api.funding(["BTC", "ETH", "SOL"], s),
      liquidations: (s: AbortSignal) => api.liquidations(["BTC", "ETH"], s),
      sentiment: (s: AbortSignal) => api.sentiment(s),
      curve: (s: AbortSignal) => api.yieldCurve(s),
      calendar: (s: AbortSignal) => api.calendar(undefined, s),
      chokepoints: (s: AbortSignal) => api.chokepoints(s),
      prediction: (s: AbortSignal) => api.prediction(s),
      energy: (s: AbortSignal) => api.energyStocks(s),
      note: (s: AbortSignal) => api.marketNote(s),
    }),
    [api],
  );
  const quotes = useFeed<QuoteBoard>(loaders.quotes, 60_000);
  const crypto = useFeed<CryptoAsset[]>(loaders.crypto, 120_000);
  const funding = useFeed<FundingBoard>(loaders.funding, 300_000);
  const liquidations = useFeed<LiquidationBoard>(loaders.liquidations, 120_000);
  const sentiment = useFeed<SentimentIndex[]>(loaders.sentiment, 3_600_000);
  const curve = useFeed<YieldCurve>(loaders.curve, 3_600_000);
  const calendar = useFeed<CalendarEvent[]>(loaders.calendar, 3_600_000);
  const chokepoints = useFeed<ChokepointTraffic[]>(loaders.chokepoints, 3_600_000);
  const prediction = useFeed<PredictionMarket[]>(loaders.prediction, 300_000);
  const energy = useFeed<EnergyBoard>(loaders.energy, 3_600_000);
  const note = useFeed<MarketNote>(loaders.note, 900_000);

  const rows = useMemo<MarketRow[]>(
    () => [
      ...(quotes.data?.items ?? []).map(quoteRow),
      ...(crypto.data ?? [])
        .filter((c) => ["btc", "eth"].includes(c.symbol.toLowerCase()))
        .map(cryptoRow),
    ],
    [quotes.data, crypto.data],
  );
  const bySymbol = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const grouped = byGroup(rows, (r) => r.group).filter(([g]) => group === "All" || g === group);
  const shownCount = grouped.reduce((n, [, list]) => n + list.length, 0);
  const upcoming = (calendar.data ?? [])
    .filter((e) => (e.impact === "high" || e.impact === "medium") && Date.parse(e.at) > Date.now())
    .slice(0, 7);
  const select = useCallback((s: string) => onSymbol(s), [onSymbol]);

  return (
    <main className="page" aria-label="Markets">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <h1>Markets</h1>
            <p>Prices next to the events that move them.</p>
          </div>
          <div
            className="page-meta"
            title="Regular hours; holidays and lunch breaks are not modelled"
          >
            <Sessions />
            <span className="tag">Delayed prices</span>
          </div>
        </div>

        <fieldset className="strip glass">
          <legend className="sr-only">Headline instruments</legend>
          {STRIP.map((s) => {
            const r = bySymbol.get(s);
            const change = formatChange(r?.changePct);
            return (
              <button key={s} type="button" aria-pressed={selected === s} onClick={() => select(s)}>
                <span className="name">{r?.name ?? s}</span>
                <span className="val">{r ? formatPrice(r.price) : "—"}</span>
                <span className={change.tone}>{change.text}</span>
              </button>
            );
          })}
        </fieldset>

        {note.data && (
          <section className="market-note" aria-label="Market note">
            <strong>Market note</strong>
            <span>{note.data.text}</span>
            <span
              className="by"
              title={`Facts computed by Argus:\n${note.data.facts.join("\n")}${
                note.data.rejected.length
                  ? `\n\nThe model's text was discarded: it added ${note.data.rejected.join(", ")}.`
                  : ""
              }`}
            >
              {formatRelative(note.data.generated_at)} ·{" "}
              {note.data.written_by === "template"
                ? "figures by Argus, no model"
                : `figures by Argus, words by ${note.data.written_by}`}
            </span>
          </section>
        )}
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="card" aria-label="Instruments">
            <div
              className="card-pad"
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
            >
              <Segmented small label="Asset group">
                {(["All", ...MARKET_GROUPS] as const).map((g) => (
                  <button
                    key={g}
                    type="button"
                    aria-pressed={group === g}
                    onClick={() => setGroup(g)}
                  >
                    {g === "Metals & agriculture" ? "Metals & ags" : g}
                  </button>
                ))}
              </Segmented>
              <span className="muted">{shownCount} instruments</span>
            </div>
            {quotes.error != null && !quotes.data && (
              <div className="card-pad">
                <Unavailable what="Quotes" error={quotes.error} />
              </div>
            )}
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Symbol</th>
                  <th scope="col">Name</th>
                  <th scope="col" className="num">
                    Last
                  </th>
                  <th scope="col" className="num">
                    Change
                  </th>
                  <th scope="col" className="num">
                    %
                  </th>
                  <th scope="col">Day range</th>
                  <th scope="col">30 sessions</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map(([g, list]) => [
                  group === "All" ? (
                    <tr key={`h-${g}`} className="group-row">
                      <td colSpan={7}>{g}</td>
                    </tr>
                  ) : null,
                  ...list.map((r) => {
                    const change = formatChange(r.changePct);
                    const digits = priceDigits(r.price);
                    const pos = rangePosition(r);
                    return (
                      <tr
                        key={r.symbol}
                        className="row"
                        aria-selected={selected === r.symbol}
                        tabIndex={0}
                        onClick={() => select(r.symbol)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            select(r.symbol);
                          }
                        }}
                      >
                        <td className="mono muted">{r.symbol}</td>
                        <td>
                          {r.name}
                          <span className="sub">{r.unit ?? ""}</span>
                        </td>
                        <td className="num">{formatPrice(r.price, digits)}</td>
                        <td className={`num ${change.tone}`}>{formatSigned(r.change, digits)}</td>
                        <td className="num">
                          <span className={`change-pill ${change.tone}`}>{change.text}</span>
                        </td>
                        <td>
                          {pos === null ? (
                            <span className="dim">—</span>
                          ) : (
                            <span
                              className="range-bar"
                              title="Where the price sits in today's session range"
                            >
                              {formatPrice(r.dayLow ?? 0, Math.min(digits, 2))}
                              <span className="track">
                                <span className="knob" style={{ left: `${pos}%` }} />
                              </span>
                              {formatPrice(r.dayHigh ?? 0, Math.min(digits, 2))}
                            </span>
                          )}
                        </td>
                        <td>
                          <Spark values={r.history} tone={change.tone} />
                        </td>
                      </tr>
                    );
                  }),
                ])}
              </tbody>
            </table>
            {quotes.data && quotes.data.missing.length > 0 && (
              <p
                className="notice notice-warn card-pad"
                title={quotes.data.missing.map((m) => `${m.key}: ${m.error}`).join("\n")}
              >
                ▲ Missing right now: {quotes.data.missing.map((m) => m.key).join(", ")}
              </p>
            )}
          </section>
          <AssetPanel api={api} symbol={selected} row={bySymbol.get(selected)} />
        </div>

        <div className="grid-3" style={{ marginTop: 16 }}>
          <section className="card card-pad" aria-labelledby="mk-chokepoints">
            <div className="card-title">
              <h2 id="mk-chokepoints">Chokepoints</h2>
              <span>ships / day, last 7 d vs same week last year</span>
            </div>
            {chokepoints.error != null && !chokepoints.data && (
              <Unavailable what="Chokepoint traffic" error={chokepoints.error} />
            )}
            <ul className="list">
              {chokepoints.data?.slice(0, 7).map((c) => {
                const status = trafficStatus(c);
                const change = formatChange(c.change_vs_last_year_pct);
                const ratio = c.last_year_avg
                  ? Math.min(1.3, c.last_7d_avg / c.last_year_avg) / 1.3
                  : null;
                const glyph =
                  status === "halted" || status === "severe"
                    ? "■"
                    : status === "reduced"
                      ? "▲"
                      : "●";
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="list-button"
                      onClick={() => onFocusPoint(c.position.lat, c.position.lon, "chokepoints")}
                    >
                      <span>
                        {c.name}
                        <span className="sub muted" style={{ display: "block", fontSize: 12 }}>
                          <span aria-hidden="true">{glyph}</span> {TRAFFIC_LABELS[status]} ·{" "}
                          {c.last_7d_avg} vs {c.last_year_avg ?? "—"}
                        </span>
                      </span>
                      <span className={`num ${change.tone}`}>{change.text}</span>
                    </button>
                    {ratio !== null && (
                      <div className="meter" aria-hidden="true">
                        <span
                          className="fill"
                          style={{
                            width: `${ratio * 100}%`,
                            background: change.tone === "down" ? "#E5484D" : "#7FB069",
                          }}
                        />
                        <i className="median" style={{ left: `${100 / 1.3}%` }} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            {chokepoints.data?.[0] && (
              <p className="notice" style={{ marginTop: 8 }}>
                IMF PortWatch, data as of {chokepoints.data[0].latest_date}. Click to show on the
                map.
              </p>
            )}
          </section>

          <section className="card card-pad" aria-labelledby="mk-prediction">
            <div className="card-title">
              <h2 id="mk-prediction">Prediction markets</h2>
              <span>Polymarket · crowd prices</span>
            </div>
            {prediction.error != null && !prediction.data && (
              <p className="notice notice-warn">
                ▲ Polymarket is unreachable from this server. It is blocked by law in some countries
                (France among them); Argus does not work around such blocks.
              </p>
            )}
            <ul className="list">
              {prediction.data?.slice(0, 5).map((m) => {
                const yes = m.outcomes[0];
                return (
                  <li key={m.id}>
                    <a
                      href={m.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="story-title"
                    >
                      {m.question}
                    </a>
                    {yes && (
                      <div className="meter" aria-hidden="true">
                        <span
                          className="fill"
                          style={{ width: `${yes.probability * 100}%`, background: "#F58A3D" }}
                        />
                      </div>
                    )}
                    <div className="story-meta">
                      {m.outcomes.map((o) => (
                        <span key={o.label}>
                          {o.label} {(o.probability * 100).toFixed(0)} %
                        </span>
                      ))}
                      {m.volume_24h_usd !== null && (
                        <span>24 h vol {formatUsd(m.volume_24h_usd)}</span>
                      )}
                    </div>
                    {canAnalyse && <PredictionAnalysis api={api} marketId={m.id} />}
                  </li>
                );
              })}
            </ul>
            <p className="notice" style={{ marginTop: 8 }}>
              Prices are what traders pay, not forecasts of record.
              {canAnalyse
                ? " “Analyse” checks whether Argus' own feeds lean the same way — or not at all."
                : " Choose a model in Sources to check them against Argus' own feeds."}
            </p>
          </section>

          <section className="card card-pad" aria-labelledby="mk-calendar">
            <div className="card-title">
              <h2 id="mk-calendar">Calendar</h2>
              <span>high and medium impact · UTC</span>
            </div>
            {calendar.error != null && !calendar.data && (
              <Unavailable what="Calendar" error={calendar.error} />
            )}
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Event</th>
                  <th scope="col" className="num">
                    Fcst.
                  </th>
                  <th scope="col" className="num">
                    Prev.
                  </th>
                </tr>
              </thead>
              <tbody>
                {upcoming.map((e) => (
                  <tr key={`${e.title}-${e.at}-${e.currency}`}>
                    <td>
                      <time dateTime={e.at} title={formatUtc(e.at)}>
                        {new Date(e.at).toLocaleString("en-GB", {
                          weekday: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: "UTC",
                        })}
                      </time>
                      <span className="sub">{formatRelative(e.at)}</span>
                    </td>
                    <td>
                      <span className={e.impact === "high" ? "tag tag-warn" : "tag"}>
                        {e.impact === "high" ? "▲ high" : "medium"}
                      </span>{" "}
                      <strong>{e.currency}</strong> {e.title}
                    </td>
                    <td className="num">{e.forecast ?? "—"}</td>
                    <td className="num">{e.previous ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {calendar.data && upcoming.length === 0 && (
              <p className="notice">No high or medium-impact release left this week.</p>
            )}
          </section>
        </div>

        <div className="grid-3" style={{ marginTop: 16 }}>
          <section className="card card-pad" aria-labelledby="mk-energy">
            <div className="card-title">
              <h2 id="mk-energy">US energy inventories</h2>
              <span>EIA, weekly · vs same week of the last 5 years</span>
            </div>
            {energy.error != null && !energy.data && (
              <Unavailable what="Inventories" error={energy.error} />
            )}
            <ul className="list">
              {energy.data?.items.map((s) => {
                const vs = formatChange(s.vs_five_year_pct);
                return (
                  <li key={s.id} className="list-button">
                    <span>
                      {s.name}
                      <span className="sub muted" style={{ display: "block", fontSize: 12 }}>
                        {formatPrice(s.latest.value, 0)} {s.unit} · week{" "}
                        {formatSigned(s.week_change, 0)}
                      </span>
                    </span>
                    <span
                      className="num"
                      title="vs five-year average (neither good nor bad in itself)"
                    >
                      {vs.text}
                    </span>
                  </li>
                );
              })}
            </ul>
            {energy.data?.items[0] && (
              <p className="notice" style={{ marginTop: 8 }}>
                Week ending {energy.data.items[0].latest.period}.
                {energy.data.missing.length > 0 &&
                  ` Missing: ${energy.data.missing.map((m) => m.key.replace("_", " ")).join(", ")} (the demo key allows few calls; see Sources).`}
              </p>
            )}
          </section>

          <section className="card card-pad" aria-labelledby="mk-derivatives">
            <div className="card-title">
              <h2 id="mk-derivatives">Crypto derivatives</h2>
              <span>perpetual futures</span>
            </div>
            {funding.data && funding.data.items.length > 0 && (
              <ul className="list" title="Positive: longs pay shorts (crowded long). Annualised.">
                {funding.data.items.map((f) => (
                  <li key={f.symbol} className="list-button">
                    <span>
                      {f.symbol} funding <span className="muted">· {f.exchange}</span>
                    </span>
                    <span className="num">{f.annualized_pct.toFixed(1)} % / yr</span>
                  </li>
                ))}
              </ul>
            )}
            {liquidations.error != null && !liquidations.data && (
              <Unavailable what="Liquidations" error={liquidations.error} />
            )}
            {liquidations.data?.items.map((l) => (
              <div key={l.symbol} style={{ marginTop: 10 }}>
                <div className="list-button">
                  <span>{l.symbol} liquidations</span>
                  <span className="num">
                    <span className="down">longs {formatUsd(l.long_usd)}</span> ·{" "}
                    <span className="up">shorts {formatUsd(l.short_usd)}</span>
                  </span>
                </div>
                <p className="notice" title={l.note}>
                  {l.count} orders
                  {l.since && l.until
                    ? ` between ${formatUtc(l.since).slice(11, 16)} and ${formatUtc(l.until).slice(11, 16)} UTC`
                    : ""}{" "}
                  · {l.exchange.toUpperCase()} only, a sample.
                </p>
              </div>
            ))}
          </section>

          <section className="card card-pad" aria-labelledby="mk-macro">
            <div className="card-title">
              <h2 id="mk-macro">Macro</h2>
              <span>US Treasury · alternative.me</span>
            </div>
            {curve.data && <YieldCurveChart curve={curve.data} />}
            {curve.error != null && !curve.data && (
              <Unavailable what="Yield curve" error={curve.error} />
            )}
            {sentiment.data?.map((s) => (
              <div key={s.id} className="list-button" style={{ marginTop: 10 }}>
                <span>{s.name}</span>
                <span className="num">
                  <strong>{s.latest.value}</strong> · {s.latest.label}
                </span>
              </div>
            ))}
            <p className="notice" style={{ marginTop: 8 }}>
              Equity Fear & Greed is not available from an open source yet.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}

function YieldCurveChart({ curve }: { curve: YieldCurve }) {
  const pts = curve.points;
  if (pts.length < 2) return null;
  const rates = pts.map((p) => p.rate_pct);
  const min = Math.min(...rates) - 0.1;
  const max = Math.max(...rates) + 0.1;
  const maxYears = Math.log1p(Math.max(...pts.map((p) => p.years)));
  const x = (years: number) => (Math.log1p(years) / maxYears) * 100;
  const y = (rate: number) => 40 - ((rate - min) / (max - min)) * 36 - 2;
  const two = pts.find((p) => p.tenor === "2 Yr");
  const ten = pts.find((p) => p.tenor === "10 Yr");
  return (
    <figure style={{ margin: 0 }}>
      <svg
        viewBox="0 0 100 40"
        width="100%"
        height="70"
        preserveAspectRatio="none"
        role="img"
        aria-label="US Treasury yield curve"
      >
        <polyline
          points={pts.map((p) => `${x(p.years).toFixed(1)},${y(p.rate_pct).toFixed(1)}`).join(" ")}
          fill="none"
          stroke="#F58A3D"
          strokeWidth="1.6"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <figcaption className="list-button">
        <span>
          2 y {two?.rate_pct ?? "—"} % · 10 y {ten?.rate_pct ?? "—"} %
        </span>
        {curve.inverted_2y_10y === true ? (
          <span className="tag tag-warn">▲ inverted</span>
        ) : (
          <span className="tag">normal slope</span>
        )}
      </figcaption>
      <p className="notice">Curve of {curve.date}, 1 month to 30 years (log scale).</p>
    </figure>
  );
}
