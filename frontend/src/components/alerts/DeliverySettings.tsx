"use client";

import { useEffect, useState } from "react";
import { keyToBytes, pushSupported, subscriptionConfig } from "@/features/alerts/push";
import { type ApiClient, ApiError } from "@/lib/api/client";
import type { AlertChannel, AlertSettings } from "@/lib/api/types";

interface Props {
  api: ApiClient;
  channels: readonly AlertChannel[];
  onChannelsChanged(): void;
}

const hhmm = (t: string | null | undefined) => (t ? t.slice(0, 5) : "");

/** Quiet hours, and this device as a push channel. */
export function DeliverySettings({ api, channels, onChannelsChanged }: Props) {
  const [settings, setSettings] = useState<AlertSettings | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [pushState, setPushState] = useState<"idle" | "busy" | "unsupported">("idle");
  const zones =
    typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  useEffect(() => {
    api.alertSettings().then(
      (s) => {
        setSettings(s);
        setStart(hhmm(s.quiet_start));
        setEnd(hhmm(s.quiet_end));
      },
      () => setStatus("Settings are unavailable."),
    );
    if (!pushSupported(typeof window === "undefined" ? undefined : window))
      setPushState("unsupported");
  }, [api]);

  const save = async (patch: Partial<AlertSettings>) => {
    if (!settings) return;
    try {
      const next = await api.saveAlertSettings({
        ...settings,
        quiet_start: start || null,
        quiet_end: end || null,
        ...patch,
      });
      setSettings(next);
      setStatus(
        next.quiet_start && next.quiet_end
          ? `Quiet ${hhmm(next.quiet_start)}–${hhmm(next.quiet_end)} (${next.timezone}): channels wait, the app still shows everything.`
          : "No quiet hours.",
      );
    } catch {
      setStatus("The server refused these settings.");
    }
  };

  const subscribe = async () => {
    setPushState("busy");
    try {
      const { public_key } = await api.pushKey();
      const registration = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      if ((await Notification.requestPermission()) !== "granted") {
        setStatus("Notifications were not allowed in this browser.");
        return;
      }
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyToBytes(public_key) as BufferSource,
      });
      await api.createAlertChannel({
        name: `This browser (${navigator.platform || "device"})`.slice(0, 60),
        kind: "web_push",
        config: subscriptionConfig(subscription.toJSON()),
      });
      setStatus("This device will receive alerts, even with Argus closed. Pick it in a rule.");
      onChannelsChanged();
    } catch (error) {
      setStatus(
        error instanceof ApiError
          ? "Web Push is off on the server."
          : `Could not subscribe: ${error instanceof Error ? error.message : "unknown error"}`,
      );
    } finally {
      setPushState((s) => (s === "busy" ? "idle" : s));
    }
  };

  const pushChannels = channels.filter((c) => c.kind === "web_push").length;

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="card-title">
        <h2>Delivery</h2>
        <span>quiet hours · this device</span>
      </div>
      <form
        className="stack"
        style={{ gap: 8 }}
        aria-label="Quiet hours"
        onSubmit={(e) => {
          e.preventDefault();
          void save({});
        }}
      >
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="field" htmlFor="quiet-start">
            <span>Quiet from</span>
            <input
              id="quiet-start"
              className="input"
              type="time"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label className="field" htmlFor="quiet-end">
            <span>to</span>
            <input
              id="quiet-end"
              className="input"
              type="time"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <label className="field" htmlFor="quiet-zone">
            <span>Time zone</span>
            <select
              id="quiet-zone"
              className="input"
              value={settings?.timezone ?? "UTC"}
              onChange={(e) => void save({ timezone: e.target.value })}
            >
              {[...new Set(["UTC", localZone, ...zones])].map((z) => (
                <option key={z} value={z}>
                  {z}
                  {z === localZone ? " (this device)" : ""}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn">
            Save
          </button>
        </div>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={settings?.critical_breaks_quiet ?? true}
            onChange={(e) => void save({ critical_breaks_quiet: e.target.checked })}
          />
          Critical alerts (■) still go through
        </label>
      </form>
      <div className="hint">
        {pushState === "unsupported" ? (
          "This browser cannot receive push notifications."
        ) : (
          <button
            type="button"
            className="btn btn-s"
            disabled={pushState === "busy"}
            onClick={() => void subscribe()}
          >
            {pushState === "busy" ? "Subscribing…" : "Receive alerts on this device (Web Push)"}
          </button>
        )}{" "}
        {pushChannels > 0 && <span className="dim">{pushChannels} device(s) subscribed.</span>}
      </div>
      {status && (
        <p className="hint" aria-live="polite">
          {status}
        </p>
      )}
    </div>
  );
}
