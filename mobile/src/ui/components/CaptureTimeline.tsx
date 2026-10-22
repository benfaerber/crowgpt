import { useMemo, useRef, useState } from "react";
import { PanResponder, StyleSheet, Text, View } from "react-native";

import { colorForCall, type FleetConfig } from "../../domain/config";
import type { DetectedCall } from "../../net/serverTypes";
import { cropFromDrag, MIN_CROP_SPAN_SEC } from "./dragCrop";
import { colors, radius, spacing } from "../theme";

/**
 * Call-type colours come from the served config — see domain/config.ts. They
 * used to be a table here, which meant the phone and the dashboard each kept
 * their own palette and agreed only by coincidence, and an operator-defined
 * label like "mobbing" fell to grey because this table had never heard of it.
 */

/** Where a touch lands, in seconds, clamped to the recording. */
function at(x: number, width: number, span: number): number {
  return Math.max(0, Math.min(span, (x / width) * span));
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

const HEIGHT = 132;
const BARS = 90;
/** Touch width of a trim handle. The visible bar is much thinner. */
const HANDLE_HIT = 44;

/** Resample the server's envelope to a fixed bar count so it fits any width. */
function resample(waveform: number[], buckets: number): number[] {
  if (waveform.length === 0) return [];
  return Array.from({ length: buckets }, (_, index) => {
    const from = Math.floor((index / buckets) * waveform.length);
    const to = Math.max(from + 1, Math.floor(((index + 1) / buckets) * waveform.length));
    let peak = 0;
    for (let i = from; i < to && i < waveform.length; i += 1) peak = Math.max(peak, waveform[i]);
    return Math.min(1, peak);
  });
}

/**
 * The capture's waveform with detected calls banded over it, in the same shape
 * as the demo dashboard's timeline.
 *
 * The point is to make a detection inspectable rather than just listed: you can
 * see where in the recording a call sits, how long it ran, and tap it to hear
 * that exact moment. A list of species names alone can't be checked against the
 * audio.
 */
export function CaptureTimeline({
  config,
  waveform,
  calls,
  earLabels,
  duration,
  position,
  crop,
  onCropChange,
  onSeek,
  onScrub,
}: {
  /** The served vocabulary, for call colours. */
  config: FleetConfig;
  waveform: number[];
  calls: DetectedCall[];
  /** By-ear labels — calls the analyzer missed, banded from below so a
   *  human mark never masquerades as a detection. */
  earLabels?: { startSec: number; endSec: number; callType: string }[];
  duration: number;
  position: number;
  /** Shades everything outside the span that will actually be uploaded. */
  crop?: { startSec?: number; endSec?: number };
  /** Supplying this makes the trim handles draggable. Fired on release. */
  onCropChange?: (crop: { startSec: number; endSec: number }) => void;
  /** Committed on release — the moment that may also start playback. */
  onSeek: (seconds: number) => void;
  /** Fired continuously while a finger is down, so the playhead follows it. */
  onScrub?: (seconds: number) => void;
}) {
  const [width, setWidth] = useState(0);
  // The pan responder is memoised, so it would capture the first width it ever
  // saw — which is zero, before layout.
  const widthRef = useRef(0);
  widthRef.current = width;
  // Live values while a handle is held. The committed crop only moves on
  // release, so a drag can be abandoned and the store isn't written per frame.
  const [dragging, setDragging] = useState<{ start: number; end: number } | null>(null);
  // Live geometry, rewritten every render.
  const geometry = useRef({ width: 0, span: 1, start: 0, end: 1 });
  // Frozen at touch-down. A gesture's dx is cumulative from where the finger
  // landed, so it has to be added to where the handle *was* — measuring against
  // the live position instead adds the whole delta again on every frame, which
  // makes the handle accelerate away.
  const anchor = useRef({ start: 0, end: 1, width: 1, span: 1 });
  // Called on release. Held in a ref because the responder is built once, and a
  // callback captured from the first render would go stale.
  const commit = useRef(onCropChange);
  commit.current = onCropChange;
  const bars = resample(waveform, BARS);
  const span = duration > 0 ? duration : 1;

  const committedStart = crop?.startSec ?? 0;
  const committedEnd = crop?.endSec ?? span;
  const startSec = dragging ? dragging.start : committedStart;
  const endSec = dragging ? dragging.end : committedEnd;
  geometry.current = { width, span, start: startSec, end: endSec };

  const handleResponder = (which: "start" | "end") =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      // Claim the gesture so the tap-to-seek underneath doesn't also fire.
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => {
        const g = geometry.current;
        anchor.current = { start: g.start, end: g.end, width: g.width, span: g.span };
        setDragging({ start: g.start, end: g.end });
      },
      onPanResponderMove: (_event, gesture) => {
        setDragging(cropFromDrag(anchor.current, which, gesture.dx));
      },
      onPanResponderRelease: () => {
        setDragging((current) => {
          if (current) commit.current?.({ startSec: current.start, endSec: current.end });
          return null;
        });
      },
      onPanResponderTerminate: () => setDragging(null),
    });

  const startHandle = useMemo(() => handleResponder("start"), []);
  const endHandle = useMemo(() => handleResponder("end"), []);
  /**
   * Scrubbing across the trace.
   *
   * `onScrub` fires continuously so the playhead follows the finger, and
   * `onSeek` fires once on release — which is what decides whether playback
   * starts. Firing the second on every frame would start the audio the instant
   * a finger moved, which is not what dragging a scrubber means anywhere else.
   */
  const scrub = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (event) => {
          if (widthRef.current > 0) {
            onScrub?.(at(event.nativeEvent.locationX, widthRef.current, span));
          }
        },
        onPanResponderMove: (event) => {
          if (widthRef.current > 0) {
            onScrub?.(at(event.nativeEvent.locationX, widthRef.current, span));
          }
        },
        onPanResponderRelease: (event) => {
          if (widthRef.current > 0) {
            onSeek(at(event.nativeEvent.locationX, widthRef.current, span));
          }
        },
      }),
    [onScrub, onSeek, span],
  );

  const step = span > 60 ? 15 : span > 20 ? 5 : 2;
  const ticks: number[] = [];
  for (let t = step; t < span; t += step) ticks.push(t);

  return (
    <View style={styles.wrapper}>
      <View
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        // Drag, not just tap. Finding a two-second call in a two-minute
        // recording by tapping is a guess repeated until it lands; scrubbing is
        // how anybody actually looks for a sound. The crop handles are children
        // and are asked first, so they still win their own gestures.
        {...scrub.panHandlers}
        style={styles.canvas}
      >
        {/* Bands sit behind the waveform so the trace stays readable over them. */}
        {calls.map((call, index) => {
          const start = typeof call.start_sec === "number" ? call.start_sec : 0;
          const end = typeof call.end_sec === "number" ? call.end_sec : start;
          const color = colorForCall(config, call.call_type);
          return (
            <View
              key={index}
              pointerEvents="none"
              style={[
                styles.band,
                {
                  left: `${(start / span) * 100}%`,
                  width: `${Math.max(1.5, ((end - start) / span) * 100)}%`,
                  backgroundColor: `${color}22`,
                  borderTopColor: color,
                },
              ]}
            >
              <Text numberOfLines={1} style={[styles.bandLabel, { color }]}>
                {call.call_type ?? call.species}
              </Text>
            </View>
          );
        })}

        {/* By-ear marks band from the bottom edge, detections from the top:
            the same span can carry both without either hiding the other. */}
        {(earLabels ?? []).map((mark, index) => {
          const color = colorForCall(config, mark.callType);
          return (
            <View
              key={`ear-${index}`}
              pointerEvents="none"
              style={[
                styles.earBand,
                {
                  left: `${(mark.startSec / span) * 100}%`,
                  width: `${Math.max(1.5, ((mark.endSec - mark.startSec) / span) * 100)}%`,
                  backgroundColor: `${color}14`,
                  borderBottomColor: color,
                },
              ]}
            >
              <Text numberOfLines={1} style={[styles.earBandLabel, { color }]}>
                {mark.callType} · by ear
              </Text>
            </View>
          );
        })}

        <View style={styles.waveRow} pointerEvents="none">
          {bars.length === 0 ? (
            <Text style={styles.empty}>No waveform yet</Text>
          ) : (
            bars.map((value, index) => (
              <View
                key={index}
                style={[styles.bar, { height: Math.max(2, value * HEIGHT * 0.72) }]}
              />
            ))
          )}
        </View>

        {ticks.map((tick) => (
          <View key={tick} pointerEvents="none" style={[styles.tick, { left: `${(tick / span) * 100}%` }]}>
            <View style={styles.tickMark} />
            <Text style={styles.tickLabel}>{clock(tick)}</Text>
          </View>
        ))}

        {startSec > 0 ? (
          <View pointerEvents="none" style={[styles.trimmed, { left: 0, width: `${(startSec / span) * 100}%` }]} />
        ) : null}
        {endSec < span ? (
          <View pointerEvents="none" style={[styles.trimmed, { left: `${(endSec / span) * 100}%`, right: 0 }]} />
        ) : null}

        {onCropChange && width > 0 ? (
          <>
            {/* The grab area is far wider than the visible bar — a 2px target is
                unusable with a thumb, especially one-handed in the field. */}
            <View
              {...startHandle.panHandlers}
              style={[styles.handleHit, { left: (startSec / span) * width - HANDLE_HIT / 2 }]}
            >
              <View style={[styles.handleBar, styles.handleBarLeft]}>
                <View style={styles.grip} />
              </View>
            </View>
            <View
              {...endHandle.panHandlers}
              style={[styles.handleHit, { left: (endSec / span) * width - HANDLE_HIT / 2 }]}
            >
              <View style={[styles.handleBar, styles.handleBarRight]}>
                <View style={styles.grip} />
              </View>
            </View>

            {dragging ? (
              <View pointerEvents="none" style={styles.dragReadout}>
                <Text style={styles.dragReadoutText}>
                  {clock(startSec)} – {clock(endSec)}  ·  {(endSec - startSec).toFixed(1)}s
                </Text>
              </View>
            ) : null}
          </>
        ) : null}

        <View
          pointerEvents="none"
          style={[styles.playhead, { left: `${Math.min(100, (position / span) * 100)}%` }]}
        />
      </View>

      {calls.length > 0 && (
        <View style={styles.legend}>
          {[...new Set(calls.map((call) => call.call_type ?? "species only"))].map((type) => (
            <View key={type} style={styles.legendItem}>
              <View
                style={[
                  styles.dot,
                  { backgroundColor: colorForCall(config, type === "species only" ? null : type) },
                ]}
              />
              <Text style={styles.legendText}>{type}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.sm },
  canvas: {
    height: HEIGHT,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.md,
    overflow: "hidden",
    justifyContent: "center",
  },
  band: { position: "absolute", top: 0, bottom: 0, borderTopWidth: 3 },
  bandLabel: { fontSize: 10, fontWeight: "700", paddingLeft: 3, paddingTop: 5 },
  earBand: {
    position: "absolute", top: 0, bottom: 0, borderBottomWidth: 3,
    justifyContent: "flex-end",
  },
  earBandLabel: { fontSize: 10, fontWeight: "700", paddingLeft: 3, paddingBottom: 5 },
  waveRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    height: "100%",
    paddingHorizontal: 2,
  },
  bar: { flex: 1, marginHorizontal: 0.5, backgroundColor: "#3a414c", borderRadius: 1 },
  empty: { color: colors.textFaint, fontSize: 12, alignSelf: "center" },
  tick: { position: "absolute", bottom: 0, alignItems: "flex-start" },
  tickMark: { width: 1, height: 6, backgroundColor: colors.textFaint, marginLeft: 0 },
  tickLabel: { color: colors.textFaint, fontSize: 9, paddingLeft: 2 },
  playhead: { position: "absolute", top: 0, bottom: 0, width: 1.5, backgroundColor: colors.text },
  // What lies outside the crop is dimmed rather than hidden, so you can see
  // what you are discarding and put it back.
  trimmed: { position: "absolute", top: 0, bottom: 0, backgroundColor: "rgba(8,11,16,0.72)" },
  handleHit: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: HANDLE_HIT,
    alignItems: "center",
    justifyContent: "center",
  },
  handleBar: { width: 4, height: "100%", backgroundColor: colors.warn, alignItems: "center", justifyContent: "center" },
  handleBarLeft: { borderTopLeftRadius: 2, borderBottomLeftRadius: 2 },
  handleBarRight: { borderTopRightRadius: 2, borderBottomRightRadius: 2 },
  grip: {
    width: 14,
    height: 30,
    borderRadius: 7,
    backgroundColor: colors.warn,
    borderWidth: 2,
    borderColor: colors.surfaceDeep,
  },
  dragReadout: {
    position: "absolute",
    top: 6,
    alignSelf: "center",
    backgroundColor: "rgba(8,11,16,0.85)",
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  dragReadoutText: { color: colors.text, fontSize: 12, fontWeight: "700", fontVariant: ["tabular-nums"] },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { color: colors.textMuted, fontSize: 11 },
});
