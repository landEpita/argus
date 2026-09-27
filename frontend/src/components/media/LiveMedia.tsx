"use client";

import { useEffect, useRef, useState } from "react";

export type MediaKind = "image" | "video" | "hls" | "youtube";

interface Props {
  kind: MediaKind;
  url: string;
  title: string;
  /** Poster for video, and what an image refreshes from. */
  still?: string | null;
  /** How often a still is re-fetched, in ms. */
  refreshMs?: number;
  /** Called instead of showing the failure, e.g. to move on to another stream. */
  onFail?: () => void;
}

/** Cache-busting URL for a still the operator overwrites in place. */
export function refreshed(url: string, at: number): string {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Math.floor(at / 1000)}`;
}

/**
 * A live camera or channel, loaded by the browser straight from its operator.
 * HLS plays natively where the browser can (Safari), else through hls.js,
 * which is only downloaded when a stream is opened. Give it a `key` of the
 * URL so switching feeds starts from a clean state.
 */
export function LiveMedia({ kind, url, title, still, refreshMs = 60_000, onFail }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [at, setAt] = useState(() => Date.now());

  useEffect(() => {
    if (kind !== "image") return;
    const timer = setInterval(() => setAt(Date.now()), refreshMs);
    return () => {
      clearInterval(timer);
    };
  }, [kind, refreshMs]);

  useEffect(() => {
    const el = video.current;
    if (kind !== "hls" || !el) return;
    if (el.canPlayType("application/vnd.apple.mpegurl")) {
      el.src = url;
      return;
    }
    let destroy = () => {};
    let cancelled = false;
    void import("hls.js").then(({ default: Hls }) => {
      if (cancelled) return;
      if (!Hls.isSupported()) {
        setFailed(true);
        return;
      }
      const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) setFailed(true);
      });
      hls.loadSource(url);
      hls.attachMedia(el);
      destroy = () => hls.destroy();
    });
    return () => {
      cancelled = true;
      destroy();
    };
  }, [kind, url]);

  useEffect(() => {
    if (failed) onFail?.();
  }, [failed, onFail]);

  if (failed) {
    if (onFail) return null;
    return (
      <p className="note notice-warn">
        The stream did not load here.{" "}
        <a href={url} target="_blank" rel="noopener noreferrer">
          Open it at the source
        </a>
        .
      </p>
    );
  }
  if (kind === "youtube") {
    return (
      <iframe
        className="live-media"
        src={url}
        title={title}
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        referrerPolicy="strict-origin-when-cross-origin"
        sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
      />
    );
  }
  if (kind === "image") {
    return (
      // biome-ignore lint/performance/noImgElement: operator stills, not optimisable assets
      <img
        className="live-media"
        src={refreshed(url, at)}
        alt={`Latest frame: ${title}`}
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <video
      ref={video}
      className="live-media"
      src={kind === "video" ? url : undefined}
      poster={still ?? undefined}
      aria-label={title}
      autoPlay
      muted
      loop={kind === "video"}
      playsInline
      controls
      onError={() => setFailed(true)}
    />
  );
}
