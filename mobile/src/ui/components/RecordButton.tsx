import { useEffect, useRef } from "react";
import { Animated, Easing, Pressable, StyleSheet, Text, View } from "react-native";

import Feather from "@expo/vector-icons/Feather";

import { colors, radius, spacing } from "../theme";

const METER_FLOOR_DB = -80;

/**
 * Field audio sits far below full scale — a crow a few meters off peaks around
 * -15 dBFS, and its half-second RMS is ~0.01, which a linear bar renders as an
 * invisible 1%. Map dBFS onto the track so the meter has usable travel.
 *
 * The floor is -80 rather than -60 because capture runs on UNPROCESSED, which on
 * our phones sits ~17 dB below VOICE_RECOGNITION; a -60 floor would park normal
 * field audio in the bottom tenth of the bar again.
 */
function meterFraction(level: number): number {
  if (level <= 0) return 0;
  const db = 20 * Math.log10(level);
  return Math.min(1, Math.max(0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB));
}

/** 00:04:37 — hours only once there are any, because there rarely are. */
function timecode(elapsedMs: number): string {
  const total = Math.max(0, Math.floor(elapsedMs / 1000));
  const pad = (n: number) => String(n).padStart(2, "0");
  const minutes = pad(Math.floor(total / 60) % 60);
  const seconds = pad(total % 60);
  const hours = Math.floor(total / 3600);
  return hours > 0 ? `${pad(hours)}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
}

/**
 * The record button, which is the whole app.
 *
 * A camera's shape rather than a form's: a red disc inside a ring, becoming a
 * square while it runs, with a blinking tally light and a timecode. That is not
 * decoration — every one of those is doing a job that a blue rectangle labelled
 * "Record" was doing badly.
 *
 * The blink is the important one. A static red button and a running red button
 * look identical at a glance in daylight, and "was it actually recording?" is a
 * question that can only be answered afterwards, when it is too late to fix. A
 * light that moves cannot be mistaken for one that is off.
 */
export function RecordButton({
  recording,
  listening,
  bufferedMs,
  level,
  elapsedMs,
  disabled,
  micLabel,
  pocket,
  headsetArmed,
  onPress,
  onRecordVideo,
  videoDisabled,
}: {
  recording: boolean;
  /** Mic open, holding the recent past. Pressing Record reaches back into it. */
  listening?: boolean;
  /** How much past is actually held right now, in ms. */
  bufferedMs?: number;
  level: number;
  elapsedMs: number;
  disabled?: boolean;
  /** Which microphone is open, in words. */
  micLabel?: string;
  /** Pocket listening, shown only when the rolling buffer is on. */
  pocket?: { on: boolean; onChange: (next: boolean) => void };
  /** The earbud button is claimed and earbuds are connected to press it. */
  headsetArmed?: boolean;
  onPress: () => void;
  /** Filming, which is the other kind of capture. Omitted, nothing is shown. */
  onRecordVideo?: () => void;
  videoDisabled?: boolean;
}) {
  // The promise the button is making, stated before it is pressed rather than
  // discovered afterwards in a file that turned out to be longer than expected.
  const held = Math.floor((bufferedMs ?? 0) / 1000);

  const tally = useRef(new Animated.Value(1)).current;
  const halo = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!recording) {
      tally.setValue(1);
      halo.setValue(0);
      return;
    }
    // Roughly one a second, which is what a tally light does and what people
    // already read as "running".
    const blink = Animated.loop(
      Animated.sequence([
        Animated.timing(tally, {
          toValue: 0.15, duration: 520, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
        Animated.timing(tally, {
          toValue: 1, duration: 520, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
      ]),
    );
    const breathe = Animated.loop(
      Animated.sequence([
        Animated.timing(halo, {
          toValue: 1, duration: 1040, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
        Animated.timing(halo, {
          toValue: 0, duration: 1040, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
      ]),
    );
    blink.start();
    breathe.start();
    return () => {
      blink.stop();
      breathe.stop();
    };
  }, [halo, recording, tally]);

  return (
    <View style={styles.wrapper}>
      {/* The status strip: tally light, state, timecode. Reads like a
          viewfinder, which is the point — this is the row that answers "is it
          running and for how long" without being read word by word. */}
      <View style={styles.strip}>
        <Animated.View
          style={[
            styles.tally,
            recording ? styles.tallyLive : listening ? styles.tallyStandby : styles.tallyIdle,
            { opacity: recording ? tally : 1 },
          ]}
        />
        <Text style={[styles.state, recording && styles.stateLive]}>
          {recording ? "REC" : listening ? "STBY" : "READY"}
        </Text>
        {/* Zero unless it is running. `elapsedMs` keeps the last recording's
            length after a stop, and a viewfinder showing 00:15 over an idle
            microphone claims something is happening that is not. */}
        <Text style={[styles.timecode, !recording && styles.timecodeIdle]}>
          {timecode(recording ? elapsedMs : 0)}
        </Text>
        <View style={styles.meterTrack}>
          <View
            style={[styles.meterFill, { width: `${Math.round(meterFraction(level) * 100)}%` }]}
          />
        </View>
        {/* Deliberately faint and wordless: it confirms the earbud button is
            live without competing with the tally. It only appears when a press
            would actually work — setting on AND earbuds connected — because
            armed and not-armed are otherwise indistinguishable until a tap in
            the field goes unanswered. */}
        {headsetArmed ? (
          <Feather
            name="headphones"
            size={12}
            color={colors.textFaint}
            accessibilityLabel="Earbud button armed"
          />
        ) : null}
      </View>

      <View style={styles.stage}>
        {/* Breathes only while running. Behind the button and untouchable, so
            it can never eat a press. */}
        {recording ? (
          <Animated.View
            pointerEvents="none"
            style={[
              styles.halo,
              {
                opacity: halo.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0] }),
                transform: [
                  { scale: halo.interpolate({ inputRange: [0, 1], outputRange: [1, 1.35] }) },
                ],
              },
            ]}
          />
        ) : null}

        {/* Left of the record button, mirroring the camcorder on the right, so
            the two things that change what Record does sit either side of it
            rather than floating over the capture list. */}
        {pocket ? (
          <Pressable
            onPress={() => pocket.onChange(!pocket.on)}
            accessibilityRole="switch"
            accessibilityState={{ checked: pocket.on }}
            accessibilityLabel="Pocket mic"
            hitSlop={12}
            style={({ pressed }) => [
              styles.pocket,
              pocket.on && styles.pocketOn,
              pressed && styles.pressed,
            ]}
          >
            <Feather
              name="mic"
              size={22}
              color={pocket.on ? colors.warn : colors.textMuted}
            />
            <Text style={[styles.pocketLabel, pocket.on && styles.pocketLabelOn]}>
              pocket
            </Text>
          </Pressable>
        ) : null}

        <Pressable
          onPress={onPress}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={recording ? "Stop recording" : "Start recording"}
          hitSlop={16}
          style={({ pressed }) => [
            styles.ring,
            disabled && styles.disabled,
            pressed && styles.pressed,
          ]}
        >
          {/* Disc to square: the same shape language as every camera made since
              1985, and it needs no label to be understood. */}
          <View style={[styles.disc, recording && styles.discRecording]} />
        </Pressable>

        {/* Beside the record button rather than below it, in the same shape, so
            the two kinds of capture read as siblings — which they are. Smaller
            because audio is what this app is for: video is the exception, taken
            when the behaviour matters as much as the call. */}
        {onRecordVideo ? (
          <Pressable
            onPress={onRecordVideo}
            disabled={videoDisabled}
            accessibilityRole="button"
            accessibilityLabel="Record video"
            hitSlop={12}
            style={({ pressed }) => [
              styles.video,
              videoDisabled && styles.disabled,
              pressed && styles.pressed,
            ]}
          >
            {/* From the same set as the map and the gear, so the three read as
                one family rather than three separate ideas about what an icon
                is. Monochrome beside a red disc: this part of the screen has to
                stay calm. */}
            <Feather name="video" size={24} color={colors.textMuted} />
          </Pressable>
        ) : null}
      </View>

      <Text style={styles.caption}>
        {recording
          ? `Recording${micLabel ? ` · ${micLabel}` : ""} — press to stop`
          : listening
            ? [
                "Mic open",
                // Named here rather than only stamped on the capture
                // afterwards: "I thought I was on the Rode" is a discovery best
                // made before the crow calls.
                micLabel,
                held > 0 ? `reaches back ${held}s` : "buffering…",
              ]
                .filter(Boolean)
                .join(" · ")
            : "Press to record"}
      </Text>
    </View>
  );
}

const RING = 104;
const DISC = 74;

const styles = StyleSheet.create({
  wrapper: { gap: spacing.sm, alignItems: "stretch" },
  strip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  tally: { width: 10, height: 10, borderRadius: 5 },
  tallyLive: { backgroundColor: colors.recording },
  tallyStandby: { backgroundColor: colors.warn },
  tallyIdle: { backgroundColor: colors.textFaint },
  state: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.5,
    width: 46,
  },
  stateLive: { color: colors.recording },
  timecode: {
    color: colors.text,
    fontSize: 15,
    fontFamily: "monospace",
    fontVariant: ["tabular-nums"],
    letterSpacing: 1,
  },
  timecodeIdle: { color: colors.textFaint },
  meterTrack: {
    flex: 1,
    height: 6,
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    overflow: "hidden",
  },
  meterFill: { height: 6, backgroundColor: colors.good },
  stage: { alignItems: "center", justifyContent: "center", paddingVertical: spacing.sm },
  halo: {
    position: "absolute",
    width: RING,
    height: RING,
    borderRadius: RING / 2,
    backgroundColor: colors.recording,
  },
  ring: {
    width: RING,
    height: RING,
    borderRadius: RING / 2,
    borderWidth: 3,
    borderColor: colors.border,
    backgroundColor: colors.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
  },
  disc: {
    width: DISC,
    height: DISC,
    borderRadius: DISC / 2,
    backgroundColor: colors.recording,
  },
  // A rounded square, the universal stop. Smaller than the disc so the change
  // is felt as well as seen.
  discRecording: { width: 44, height: 44, borderRadius: 8 },
  pocket: {
    position: "absolute",
    left: spacing.lg,
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surfaceDeep,
    alignItems: "center",
    justifyContent: "center",
    gap: 1,
  },
  // Amber while it is holding the microphone from a pocket, which is the same
  // colour the tally light uses for standby — it is the same fact.
  pocketOn: { borderColor: colors.warn },
  pocketLabel: { color: colors.textFaint, fontSize: 8, letterSpacing: 0.5 },
  pocketLabelOn: { color: colors.warn },
  video: {
    position: "absolute",
    // Anchored to the right so the record button stays exactly centred: it is
    // the one control that should never move.
    right: spacing.lg,
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surfaceDeep,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
  disabled: { opacity: 0.4 },
  pressed: { opacity: 0.75 },
  caption: { color: colors.textMuted, fontSize: 12, textAlign: "center" },
});
