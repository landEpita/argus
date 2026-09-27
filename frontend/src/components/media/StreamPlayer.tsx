"use client";

import { useCallback, useState } from "react";
import type { Stream } from "@/lib/api/types";
import { LiveMedia } from "./LiveMedia";

interface Props {
  title: string;
  streams: readonly Stream[];
}

/**
 * Plays the first stream that loads. An HLS stream that fails moves on by
 * itself; a YouTube embed cannot report failure to the page, so the viewer
 * can move on by hand.
 */
export function StreamPlayer({ title, streams }: Props) {
  const [index, setIndex] = useState(0);
  const stream = streams[index];
  const next = useCallback(() => setIndex((i) => i + 1), []);

  if (!stream) {
    return (
      <div className="live-media live-empty">
        <p className="note notice-warn">
          No stream of {title} loads here right now
          {streams[0] && (
            <>
              {" "}
              ·{" "}
              <a href={streams[0].page} target="_blank" rel="noopener noreferrer">
                open at the source
              </a>
            </>
          )}
          .
        </p>
      </div>
    );
  }
  return (
    <div className="stream-player">
      <LiveMedia key={stream.url} kind={stream.kind} url={stream.url} title={title} onFail={next} />
      <div className="stream-meta">
        <span className="dim">
          {stream.kind === "hls" ? "Broadcaster stream" : "YouTube"}
          {streams.length > 1 && ` · ${index + 1}/${streams.length}`}
        </span>
        <span>
          {index + 1 < streams.length && (
            <button type="button" className="btn btn-ghost btn-s" onClick={next}>
              Try next stream
            </button>
          )}{" "}
          <a href={stream.page} target="_blank" rel="noopener noreferrer">
            Source
          </a>
        </span>
      </div>
    </div>
  );
}
