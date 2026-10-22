import { Feather } from "@expo/vector-icons";
import { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../theme";
import { SlideToUnlock } from "./SlideToUnlock";

function elapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * What the screen shows while a capture is locked.
 *
 * Covers everything, which is the point — the failure it prevents is a touch
 * landing on whatever happened to be under it, so leaving anything reachable
 * defeats it. There is exactly one control.
 *
 * It has to keep showing that the recording is alive, though, or the lock
 * becomes its own kind of doubt: a covered screen that said nothing would leave
 * "is it still going?" unanswerable without unlocking, which is the question the
 * blinking button exists to answer in the first place. So the timer runs, the
 * level moves, and the microphone is named.
 */
export function CaptureLock({
  elapsedMs,
  level,
  micLabel,
  onUnlock,
}: {
  elapsedMs: number;
  level: number;
  micLabel?: string;
  onUnlock: () => void;
}) {
  const pulse = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    // The same promise the record button makes: a light that moves cannot be
    // mistaken for one that is off.
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.4, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  return (
    <View style={styles.overlay}>
      <View style={styles.status}>
        <Animated.View style={[styles.dot, { opacity: pulse }]} />
        <Text style={styles.recording}>Recording</Text>
      </View>

      <Text style={styles.timer}>{elapsed(elapsedMs)}</Text>

      <View style={styles.meterTrack}>
        <View
          style={[styles.meterFill, { width: `${Math.round(Math.min(1, level) * 100)}%` }]}
        />
      </View>

      {micLabel ? <Text style={styles.mic}>{micLabel}</Text> : null}

      <View style={styles.spacer} />

      <View style={styles.lockNote}>
        <Feather name="lock" size={14} color={colors.textMuted} />
        <Text style={styles.lockText}>Screen locked so a pocket cannot stop this</Text>
      </View>

      {/* Stretched deliberately: the track's width IS the distance a thumb has
          to travel, so a narrow one is a weaker lock. */}
      <View style={styles.slide}>
        <SlideToUnlock onUnlock={onUnlock} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.background,
    paddingHorizontal: spacing.lg,
    paddingTop: 96,
    paddingBottom: 48,
    alignItems: "center",
    zIndex: 10,
  },
  status: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.recording,
  },
  recording: { color: colors.text, fontSize: 16, fontWeight: "700" },
  timer: {
    color: colors.text,
    fontSize: 64,
    fontWeight: "200",
    fontVariant: ["tabular-nums"],
    marginTop: spacing.md,
  },
  meterTrack: {
    width: "70%",
    height: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    overflow: "hidden",
    marginTop: spacing.lg,
  },
  meterFill: { height: 6, backgroundColor: colors.good },
  mic: { color: colors.textMuted, fontSize: 13, marginTop: spacing.md },
  spacer: { flex: 1 },
  lockNote: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  lockText: { color: colors.textMuted, fontSize: 12 },
  slide: { alignSelf: "stretch" },
});
