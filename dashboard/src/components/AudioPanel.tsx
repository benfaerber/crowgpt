import { useEffect, useRef, useState } from "react";

import { fetchMediaUrl, useFleetConfig } from "../api/client";
import type { Analysis, Media } from "../api/types";
import { describeMic, formatBytes } from "../format";
import { colorForCall } from "../vocab";
import { Waveform } from "./Waveform";

/**
 * Playback, the waveform, and how the recording was made.
 *
 * Renders a video element when the media is video: a clip uploaded from the
 * browser often has no separate audio track, and the analyzer reads its sound
 * through ffmpeg just the same. The waveform comes from the analysis either
 * way, so it works for both.
 *
 * `<audio>` cannot carry an Authorization header and the media route is
 * token-gated, so the bytes come through fetch and become a blob URL — which
 * has to be revoked when the panel closes, or every capture played leaks its
 * own audio.
 */
export function AudioPanel({
  audio,
  analysis,
  fallbackDuration,
}: {
  audio: Media;
  analysis: Analysis | null;
  fallbackDuration: number | null;
}) {
  const [source, setSource] = useState<string>();
  const [failure, setFailure] = useState<string>();
  const [position, setPosition] = useState(0);
  // One ref for both elements: seeking, currentTime and play() are on
  // HTMLMediaElement, so the controls below do not care which it is.
  const player = useRef<HTMLMediaElement>(null);
  const config = useFleetConfig();

  const mic = describeMic(audio.input_device, audio.input_honoured);
  const calls = analysis?.calls ?? [];
  const peaks = analysis?.waveform ?? [];
  const duration = analysis?.duration ?? fallbackDuration ?? 0;

  // Shared with the labels and detections tables — see ../vocab. It used to be
  // a copy of the same four lines here, which is how a waveform and the table
  // under it come to disagree about what colour a rattle is.
  const colorFor = (callType: string | null): string => colorForCall(config.data, callType);

  useEffect(() => {
    let url: string | undefined;
    let live = true;
    fetchMediaUrl(audio.id)
      .then((created) => {
        url = created;
        if (live) setSource(created);
        else URL.revokeObjectURL(created);
      })
      .catch((error: Error) => live && setFailure(error.message));
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [audio.id]);

  const seek = (seconds: number) => {
    if (!player.current) return;
    player.current.currentTime = seconds;
    void player.current.play();
  };

  // A second of lead-in: a call is easier to recognise with the moment before
  // it, and landing exactly on the onset usually clips the start. Same rule the
  // app uses, so the two behave identically.
  const skipToCall = (startSec: number) => seek(Math.max(0, startSec - 1));

  return (
    <>
      <div className="muted" style={{ fontSize: ".82rem" }}>
        {audio.format.toUpperCase()}
        {audio.kind === "video" ? " video" : ""}
        {audio.sample_rate ? ` · ${audio.sample_rate} Hz` : ""}
        {audio.channels ? ` · ${audio.channels}ch` : ""} · {formatBytes(audio.bytes)} ·{" "}
        {mic ? (
          <span style={mic.suspect ? { fontWeight: 700, color: "var(--warn)" } : undefined}>
            mic {mic.text}
          </span>
        ) : (
          <span className="muted">mic unknown</span>
        )}{" "}
        · sha256 {(audio.sha256 ?? "").slice(0, 12)}…
      </div>

      {failure ? <div className="note">Could not load audio — {failure}</div> : null}

      {duration > 0 ? (
        <Waveform
          peaks={peaks}
          calls={calls}
          duration={duration}
          position={position}
          colorFor={colorFor}
          onSeek={seek}
        />
      ) : null}

      {audio.kind === "video" ? (
        <video
          ref={player as React.RefObject<HTMLVideoElement>}
          controls
          src={source}
          onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
          style={{ width: "100%", marginTop: ".6rem", borderRadius: 6 }}
        />
      ) : (
        <audio
          ref={player as React.RefObject<HTMLAudioElement>}
          controls
          src={source}
          onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
          style={{ width: "100%", marginTop: ".6rem" }}
        />
      )}

      {calls.length > 0 ? (
        <div style={{ display: "flex", gap: ".4rem", flexWrap: "wrap", marginTop: ".5rem" }}>
          {calls.map((call, index) => (
            <button
              key={index}
              className="ghost"
              onClick={() => skipToCall(call.start_sec)}
              style={{
                fontSize: ".75rem",
                padding: ".25rem .6rem",
                borderColor: colorFor(call.call_type),
              }}
            >
              ▶ {call.call_type ?? call.species} @ {call.start_sec.toFixed(1)}s
            </button>
          ))}
        </div>
      ) : null}
    </>
  );
}
