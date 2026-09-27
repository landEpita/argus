import { formatCount, isRasterData } from "@/features/map/layers/types";
import type { LayerUpdate } from "@/features/map/scheduler";
import { ApiError } from "@/lib/api/client";
import { formatRelative } from "@/lib/time/relative";

/** Why a layer failed, for the status line: the API's own explanation when it gave one. */
export function errorReason(update: LayerUpdate | undefined): string | undefined {
  if (update?.status !== "error") return undefined;
  const { error } = update;
  if (error instanceof ApiError) {
    const body = (error.body ?? {}) as { error?: string; message?: string; providers?: string[] };
    if (body.message) return body.message;
    if (body.error === "upstream_unavailable") {
      return `No source answered (${(body.providers ?? []).join(", ") || "unknown"}); retrying`;
    }
    return `HTTP ${error.status}${body.error ? ` — ${body.error}` : ""}`;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

export interface LayerStatus {
  text: string;
  tone: "normal" | "warn" | "bad" | "dim";
  count: string;
}

/** The drawer's status line and count for one layer. */
export function layerStatus(
  on: boolean,
  update: LayerUpdate | undefined,
  now: number,
): LayerStatus {
  if (!on) return { text: "Off", tone: "dim", count: "" };
  switch (update?.status) {
    case "ready": {
      const count = isRasterData(update.data) ? "" : formatCount(update.data);
      const age = formatRelative(new Date(update.loadedAt).toISOString(), now);
      const valid =
        isRasterData(update.data) && update.data.validAt
          ? ` · image of ${update.data.validAt.slice(11, 16)} UTC`
          : "";
      const meta = isRasterData(update.data) ? undefined : update.data.meta;
      if (meta) {
        return {
          text: `${meta.warn ? "▲ " : ""}${meta.note} · ${age}`,
          tone: meta.warn ? "warn" : "normal",
          count,
        };
      }
      return { text: `Updated ${age}${valid}`, tone: "normal", count };
    }
    case "error":
      return { text: `▲ ${errorReason(update)}`, tone: "warn", count: "—" };
    case "unavailable":
      return { text: "○ Not configured on the server · key required", tone: "warn", count: "" };
    case "zoom":
      return { text: "Zoom in to load", tone: "dim", count: "" };
    default:
      return { text: "Loading…", tone: "dim", count: "…" };
  }
}
