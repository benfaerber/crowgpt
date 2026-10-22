import { useMemo } from "react";

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
  const mid = height / 2;

  // Bars, not a filled path: a peak envelope is a series of maxima, and
  // interpolating between them draws a shape the audio never had.
  const bars = useMemo(() => {
    if (peaks.length === 0) return [];
    const step = width / peaks.length;
    return peaks.map((peak, index) => ({
      x: index * step,
      w: Math.max(0.5, step * 0.8),
      h: Math.max(1, Math.min(1, peak) * (height - 8)),
    }));
  }, [peaks]);

  const seekFromEvent = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - box.left) / box.width;
    onSeek(Math.max(0, Math.min(1, fraction)) * duration);
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
        const x = (call.start_sec / duration) * width;
        const w = Math.max(2, ((call.end_sec - call.start_sec) / duration) * width);
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
          y={mid - bar.h / 2}
          width={bar.w}
          height={bar.h}
          fill="var(--muted)"
          opacity={0.75}
        />
      ))}

      {position != null && duration > 0 ? (
        <rect
          x={(position / duration) * width}
          y={0}
          width={2}
          height={height}
          fill="var(--accent)"
        />
      ) : null}
    </svg>
  );
}
