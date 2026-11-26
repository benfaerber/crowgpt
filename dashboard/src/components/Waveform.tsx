import { useMemo } from "react";

import { TimelineGeometry } from "../../../shared/scan";
import type { DetectedCall } from "../api/types";

/**
 * The capture's envelope with detected calls laid over it.
 *
 * Drawn from the waveform the worker already computed and stored, not
 * recomputed here — the app builds its own envelope because it must show one
 * before a capture has ever been uploaded, which is a constraint the dashboard
 * does not have. Same picture, arrived at differently.
 *
 * SVG rather than canvas: a few hundred bars, and the call bands need to be
 * hoverable and clickable, which is free in SVG and hand-rolled in canvas.
 */
export function Waveform({
  peaks,
  calls,
  duration,
  position,
  colorFor,
  onSeek,
}: {
  peaks: number[];
  calls: DetectedCall[];
  duration: number;
  /** Playhead in seconds, if the audio is loaded. */
  position?: number;
  colorFor: (callType: string | null) => string;
  onSeek: (seconds: number) => void;
}) {
  const width = 1000;
  const height = 120;
  const geometry = useMemo(() => new TimelineGeometry(duration, width, height), [duration]);
  const bars = useMemo(() => geometry.bars(peaks), [geometry, peaks]);

  const seekFromEvent = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    onSeek(geometry.secondsAt((event.clientX - box.left) / box.width));
  };

  if (peaks.length === 0 && calls.length === 0) return null;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      onClick={seekFromEvent}
      style={{
        width: "100%",
        height,
        display: "block",
        background: "var(--panel2)",
        borderRadius: 6,
        cursor: "pointer",
        marginTop: ".6rem",
      }}
    >
      {calls.map((call, index) => {
        const { x, width: w } = geometry.band(call.start_sec, call.end_sec);
        const color = colorFor(call.call_type);
        return (
          <g key={index}>
            <rect x={x} y={0} width={w} height={height} fill={color} opacity={0.16} />
            {/* A hairline at the onset: a wide band says "somewhere in here",
                and the onset is the thing you actually want to hear. */}
            <rect x={x} y={0} width={1} height={height} fill={color} opacity={0.9} />
            <title>
              {call.call_type ?? call.species} · {call.start_sec.toFixed(1)}–
              {call.end_sec.toFixed(1)}s
              {call.confidence != null ? ` · ${call.confidence.toFixed(2)}` : ""}
            </title>
          </g>
        );
      })}

      {bars.map((bar, index) => (
        <rect
          key={index}
          x={bar.x}
          y={bar.y}
          width={bar.width}
          height={bar.height}
          fill="var(--muted)"
          opacity={0.75}
        />
      ))}

      {position != null && duration > 0 ? (
        <rect
          x={geometry.x(position)}
          y={0}
          width={2}
          height={height}
          fill="var(--accent)"
        />
      ) : null}
    </svg>
  );
}
