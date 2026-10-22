import { useRef, useState } from "react";
import { Animated, PanResponder, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../theme";
import { unlockReached } from "../../domain/captureLock";

const KNOB = 56;

/**
 * Drag all the way across to unlock. The one control a locked screen offers.
 *
 * A tap cannot do this and neither can a smear. That is the whole specification:
 * the threat is a capacitive screen pressed against a damp leg in a pocket,
 * which produces taps and short drags in arbitrary directions, and a gesture
 * that has to travel most of the width of the screen in one direction without
 * being released is not something a pocket produces by accident.
 *
 * Deliberately silent. A confirmation tone would be recorded by the microphone
 * that is, by definition, open — this control only ever appears during a
 * capture, so any sound it made would end up in the corpus.
 *
 * Not a button with a confirmation dialog, which was the other option: a dialog
 * puts a second tappable thing on screen, and a pocket that produced the first
 * tap will produce the second.
 */
export function SlideToUnlock({
  label = "Slide to unlock",
  onUnlock,
}: {
  label?: string;
  onUnlock: () => void;
}) {
  const [trackWidth, setTrackWidth] = useState(0);
  const travel = Math.max(0, trackWidth - KNOB - spacing.xs * 2);
  const x = useRef(new Animated.Value(0)).current;
  // Read inside the responder, which is created once and would otherwise close
  // over the width measured before layout — zero, making every drag a no-op.
  const travelRef = useRef(0);
  travelRef.current = travel;

  const responder = useRef(
    PanResponder.create({
      // Claimed on touch-down so the knob tracks from the first pixel; a touch
      // that never travels simply releases at dx 0 and springs back. Claiming
      // the touch is not the same as accepting the unlock, and only the second
      // of those has a threshold.
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_event, gesture) => Math.abs(gesture.dx) > 4,
      onPanResponderMove: (_event, gesture) => {
        const limit = travelRef.current;
        x.setValue(Math.min(limit, Math.max(0, gesture.dx)));
      },
      onPanResponderRelease: (_event, gesture) => {
        const limit = travelRef.current;
        if (unlockReached(gesture.dx, limit)) {
          x.setValue(limit);
          onUnlock();
          return;
        }
        // Springs back rather than staying put. A knob left halfway is a
        // half-unlocked lock, and the next brush finishes the job.
        Animated.spring(x, { toValue: 0, useNativeDriver: true, bounciness: 0 }).start();
      },
      onPanResponderTerminate: () => {
        Animated.spring(x, { toValue: 0, useNativeDriver: true, bounciness: 0 }).start();
      },
    }),
  ).current;

  return (
    <View
      style={styles.track}
      onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
      accessibilityRole="adjustable"
      accessibilityLabel={label}
      accessibilityHint="Slide right to unlock the recording controls"
    >
      <Text style={styles.label}>{label}</Text>
      <Animated.View
        {...responder.panHandlers}
        style={[styles.knob, { transform: [{ translateX: x }] }]}
      >
        <Text style={styles.knobText}>›››</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: KNOB + spacing.xs * 2,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: "center",
    padding: spacing.xs,
  },
  label: {
    position: "absolute",
    alignSelf: "center",
    color: colors.textMuted,
    fontSize: 14,
    fontWeight: "600",
  },
  knob: {
    width: KNOB,
    height: KNOB,
    borderRadius: KNOB / 2,
    backgroundColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  knobText: { color: "#fff", fontSize: 18, fontWeight: "700" },
});
