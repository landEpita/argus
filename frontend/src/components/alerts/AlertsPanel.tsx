"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CHANNEL_FIELDS,
  describeRule,
  initialValues,
  paramsFrom,
  RULE_KINDS,
} from "@/features/alerts/rules";
import { type ApiClient, ApiError } from "@/lib/api/client";
import type {
  AlertChannel,
  AlertItem,
  AlertRule,
  ChannelKind,
  ChannelKindInfo,
  RuleKind,
} from "@/lib/api/types";
import { formatRelative } from "@/lib/time/relative";
import { AlertRow } from "./AlertRow";
import { DeliverySettings } from "./DeliverySettings";

interface Props {
  api: ApiClient;
  onOpenAlert(alert: AlertItem): void;
  /** Called after reading or evaluating, so the header count follows. */
  onChanged(): void;
}

const KINDS = Object.keys(RULE_KINDS) as RuleKind[];

function problem(error: unknown): string {
  if (error instanceof ApiError) {
    const body = (error.body ?? {}) as { message?: string; detail?: unknown };
    if (body.message) return body.message;
    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg.replace(/^Value error, /, "");
    }
    return `HTTP ${error.status}`;
  }
  return "Unexpected error";
}

/** Rules, channels and what fired: the phase 6 half of the Watch space. */
export function AlertsPanel({ api, onOpenAlert, onChanged }: Props) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [channels, setChannels] = useState<AlertChannel[]>([]);
  const [channelKinds, setChannelKinds] = useState<ChannelKindInfo[]>([]);
  const [feed, setFeed] = useState<AlertItem[]>([]);
  const [composer, setComposer] = useState(false);
  const [kind, setKind] = useState<RuleKind>("earthquake");
  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, string>>(initialValues("earthquake"));
  const [ruleChannels, setRuleChannels] = useState<string[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [channelKind, setChannelKind] = useState<ChannelKind>("discord");
  const [channelName, setChannelName] = useState("");
  const [channelConfig, setChannelConfig] = useState<Record<string, string>>({});
  const [notify, setNotify] = useState<NotificationPermission | "unsupported">("default");

  const reload = useCallback(async () => {
    const [r, c, k, f] = await Promise.all([
      api.alertRules(),
      api.alertChannels(),
      api.alertChannelKinds(),
      api.alerts(),
    ]);
    setRules(r);
    setChannels(c);
    setChannelKinds(k);
    setFeed(f.items);
  }, [api]);

  useEffect(() => {
    void reload().catch(() => setStatus("Alerts are unavailable right now."));
    setNotify(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  }, [reload]);

  const createRule = async () => {
    try {
      await api.createAlertRule({
        name: name.trim() || RULE_KINDS[kind].label,
        kind,
        params: paramsFrom(kind, values),
        channels: ruleChannels,
        enabled: true,
      });
      setComposer(false);
      setName("");
      setHint(null);
      await reload();
    } catch (error) {
      setHint(problem(error));
    }
  };

  const toggle = async (rule: AlertRule) => {
    await api.updateAlertRule(rule.id, { ...rule, enabled: !rule.enabled });
    await reload();
  };

  const addChannel = async () => {
    try {
      await api.createAlertChannel({
        name: channelName.trim() || channelKind,
        kind: channelKind,
        config: channelConfig,
      });
      setChannelName("");
      setChannelConfig({});
      setStatus("Channel added. Use Test to check it.");
      await reload();
    } catch (error) {
      setStatus(problem(error));
    }
  };

  const checkNow = async () => {
    setStatus("Checking the rules…");
    try {
      const r = await api.evaluateAlerts();
      setStatus(
        `${r.fired.length} new alert${r.fired.length === 1 ? "" : "s"}` +
          (r.skipped.length ? ` · not checked (source down): ${r.skipped.join(", ")}` : ""),
      );
      await reload();
      onChanged();
    } catch (error) {
      setStatus(problem(error));
    }
  };

  const unread = feed.filter((a) => !a.read).length;

  return (
    <section className="card card-pad stack" style={{ gap: 18 }} aria-label="Rules and activity">
      <div>
        <div className="card-title">
          <h2>Activity</h2>
          <span>
            {unread ? `${unread} unread · ` : ""}
            <button type="button" className="btn btn-s btn-ghost" onClick={() => void checkNow()}>
              Check now
            </button>
            {unread > 0 && (
              <button
                type="button"
                className="btn btn-s btn-ghost"
                onClick={() => void api.markAlertsRead().then(reload).then(onChanged)}
              >
                Mark all read
              </button>
            )}
          </span>
        </div>
        {status && (
          <p className="hint" aria-live="polite">
            {status}
          </p>
        )}
        {feed.length === 0 ? (
          <p className="notice">
            Nothing has fired yet. Rules are checked every two minutes; “Check now” runs them
            immediately.
          </p>
        ) : (
          <ul className="list">
            {feed.slice(0, 12).map((a) => (
              <li key={a.id}>
                <AlertRow alert={a} onOpen={onOpenAlert} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="card-title">
          <h2>Rules</h2>
          <span>
            {rules.filter((r) => r.enabled).length} of {rules.length} active ·{" "}
            <button
              type="button"
              className="btn btn-s btn-primary"
              onClick={() => setComposer((c) => !c)}
            >
              New rule
            </button>
          </span>
        </div>
        {composer && (
          <form
            className="stack"
            style={{ gap: 8, marginBottom: 12 }}
            aria-label="New rule"
            onSubmit={(e) => {
              e.preventDefault();
              void createRule();
            }}
          >
            <label className="field">
              <span>When</span>
              <select
                className="input"
                value={kind}
                onChange={(e) => {
                  const k = e.target.value as RuleKind;
                  setKind(k);
                  setValues(initialValues(k));
                  setHint(null);
                }}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {RULE_KINDS[k].label}
                  </option>
                ))}
              </select>
            </label>
            {RULE_KINDS[kind].fields.map((f) => (
              <label key={f.name} className="field" htmlFor={`rule-${f.name}`}>
                <span>{f.label}</span>
                {f.type === "select" ? (
                  <select
                    id={`rule-${f.name}`}
                    className="input"
                    value={values[f.name] ?? f.initial}
                    onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                  >
                    {f.options?.map((o, i) => (
                      <option key={o} value={o}>
                        {f.optionLabels?.[i] ?? o}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`rule-${f.name}`}
                    className="input"
                    inputMode={f.type === "number" ? "decimal" : undefined}
                    placeholder={f.placeholder}
                    value={values[f.name] ?? ""}
                    onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                  />
                )}
              </label>
            ))}
            <label className="field">
              <span>Name</span>
              <input
                className="input"
                placeholder={RULE_KINDS[kind].label}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend>Send to (always shown in the app)</legend>
              {channels.length === 0 && (
                <span className="dim">No channel yet — add one below.</span>
              )}
              {channels.map((c) => (
                <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={ruleChannels.includes(c.id)}
                    onChange={(e) =>
                      setRuleChannels(
                        e.target.checked
                          ? [...ruleChannels, c.id]
                          : ruleChannels.filter((x) => x !== c.id),
                      )
                    }
                  />
                  {c.name} <span className="dim">({c.kind})</span>
                </label>
              ))}
            </fieldset>
            {hint && <p className="hint bad">{hint}</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <button type="submit" className="btn btn-primary">
                Create rule
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setComposer(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}
        <ul className="list">
          {rules.map((r) => (
            <li key={r.id} style={{ opacity: r.enabled ? 1 : 0.5 }}>
              <div className="list-button">
                <span>
                  <strong>{r.name}</strong>
                  <span className="sub muted" style={{ display: "block", fontSize: 12 }}>
                    {describeRule(r, channels)}
                  </span>
                  <span className="sub dim" style={{ display: "block", fontSize: 11 }}>
                    {r.enabled
                      ? r.last_fired_at
                        ? `last fired ${formatRelative(r.last_fired_at)}`
                        : "never fired"
                      : "paused"}
                  </span>
                </span>
                <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <button
                    type="button"
                    className="layer-row"
                    style={{ width: "auto", padding: 0 }}
                    aria-pressed={r.enabled}
                    aria-label={`${r.enabled ? "Pause" : "Resume"} ${r.name}`}
                    onClick={() => void toggle(r)}
                  >
                    <span className="switch" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="btn btn-s btn-ghost"
                    aria-label={`Delete ${r.name}`}
                    onClick={() => void api.deleteAlertRule(r.id).then(reload)}
                  >
                    ×
                  </button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <div className="card-title">
          <h2>Channels</h2>
          <span>secrets stay on the server</span>
        </div>
        <ul className="list">
          {channels.map((c) => (
            <li key={c.id} className="list-button">
              <span>
                {c.name}{" "}
                <span className="dim">
                  · {c.kind} · {c.hint}
                </span>
              </span>
              <span>
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() =>
                    void api
                      .testAlertChannel(c.id)
                      .then((d) =>
                        setStatus(d.ok ? `● ${c.name}: test sent` : `■ ${c.name}: ${d.error}`),
                      )
                  }
                >
                  Test
                </button>
                <button
                  type="button"
                  className="btn btn-s btn-ghost"
                  aria-label={`Delete channel ${c.name}`}
                  onClick={() => void api.deleteAlertChannel(c.id).then(reload)}
                >
                  ×
                </button>
              </span>
            </li>
          ))}
        </ul>
        <form
          className="stack"
          style={{ gap: 8, marginTop: 8 }}
          aria-label="New channel"
          onSubmit={(e) => {
            e.preventDefault();
            void addChannel();
          }}
        >
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <select
              className="input"
              aria-label="Channel kind"
              value={channelKind}
              onChange={(e) => {
                setChannelKind(e.target.value as ChannelKind);
                setChannelConfig({});
              }}
            >
              {channelKinds
                .filter((k) => k.kind !== "web_push")
                .map((k) => (
                  <option key={k.kind} value={k.kind} disabled={!k.available}>
                    {k.kind}
                    {k.available ? "" : " (not configured on the server)"}
                  </option>
                ))}
            </select>
            <input
              className="input"
              style={{ flex: 1, minWidth: 100 }}
              aria-label="Channel name"
              placeholder="Name"
              value={channelName}
              onChange={(e) => setChannelName(e.target.value)}
            />
          </div>
          {CHANNEL_FIELDS[channelKind].map((f) => (
            <input
              key={f.name}
              className="input mono"
              type={f.secret ? "password" : "text"}
              autoComplete="off"
              aria-label={f.label}
              placeholder={f.label}
              value={channelConfig[f.name] ?? ""}
              onChange={(e) => setChannelConfig({ ...channelConfig, [f.name]: e.target.value })}
            />
          ))}
          <button type="submit" className="btn">
            Add channel
          </button>
        </form>
      </div>

      <DeliverySettings api={api} channels={channels} onChannelsChanged={() => void reload()} />
      <div className="hint">
        {notify === "unsupported" ? (
          "This browser cannot show notifications."
        ) : notify === "granted" ? (
          "● Notifications are allowed in this browser."
        ) : (
          <button
            type="button"
            className="btn btn-s"
            onClick={() => void Notification.requestPermission().then(setNotify)}
          >
            Allow notifications while Argus is open
          </button>
        )}{" "}
        <span className="dim">The desktop app is planned.</span>
      </div>
    </section>
  );
}
