import { useEffect, useRef } from "react";
import { ActivityIndicator, Animated, Easing, StyleSheet, Text, View } from "react-native";

import type { PendingCapture } from "../../domain/pendingCaptures";
import { colors, formatDuration, radius, spacing } from "../theme";

/**
 * A capture that exists but has not been written down yet.
 *
 * Built to the same measurements as {@link CaptureRow} on purpose — same
 * padding, same radius, same two lines, headline over meta. When the real row
 * arrives it takes this one's place without the list moving, so the change
 * reads as this row becoming the capture rather than one row vanishing and a
 * different one appearing somewhere else. Matching the geometry is the whole
 * trick; nothing else here is doing the work.
 *
 * It is deliberately not pressable. There is no capture to open yet, and a row
 * that responds to a tap by doing nothing is how a list teaches people that
 * tapping it is pointless.
 */
export function PendingCaptureRow({ pending }: { pending: PendingCapture }) {
  // Breathes, rather than sitting still. A static "Loading…" and a hung
  // "Loading…" are the same picture, and this app has already been caught once
  // showing a disabled control that looked exactly like a working one.
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1, duration: 900, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0, duration: 900, easing: Easing.inOut(Easing.quad), useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  return (
    <Animated.View
      style={[
        styles.row,
        { opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 0.62] }) },
      ]}
      accessibilityRole="progressbar"
      accessibilityLabel={
        pending.kind === "video" ? "Saving a video capture" : "Saving a capture"
      }
    >
      <View style={styles.header}>
        <Text style={styles.when} numberOfLines={1}>
          Loading…
        </Text>
        <View style={styles.badge}>
          <ActivityIndicator size="small" color={colors.textMuted} />
        </View>
      </View>

      {/* The length is already known — it came back with the closed file — so
          the placeholder states it instead of leaving a blank where the number
          will be. A row that can already say "0:08" is much harder to mistake
          for one that is stuck. */}
      <Text style={styles.meta}>
        {pending.durationMs !== undefined ? `${formatDuration(pending.durationMs)} · ` : ""}
        {pending.kind === "video" ? "video · saving" : "saving"}
      </Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  // Measurements copied from CaptureRow rather than shared, because they are
  // the same by intent and not by definition: a placeholder that quietly
  // followed a redesign of the real row would stop matching the thing it is
  // standing in for at exactly the moment somebody changed that row.
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: "dashed",
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  when: { color: colors.textMuted, fontSize: 15, fontWeight: "600", flexShrink: 1 },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2 },
  meta: { color: colors.textFaint, fontSize: 12 },
});
