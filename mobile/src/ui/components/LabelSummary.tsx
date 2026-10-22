import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import { buildLabelCards, countDecided, type DetectedSpan } from "../../domain/labelCards";
import { colors, radius, spacing } from "../theme";

/**
 * How much of this capture has been decided, and the way in.
 *
 * The labelling list used to sit here, which meant a two-minute capture put a
 * dozen calls on a screen that was already long — and deciding about a call
 * competed for attention with everything else about the recording. Deciding is
 * its own activity, so it gets its own screen; this is the door and the progress
 * bar.
 *
 * Counts come from `buildLabelCards`, the same function the deck uses. They were
 * computed two different ways once — labels here, cards there — and reported 9
 * and 10 for the same recording. Two formulas that agree today are a bug
 * waiting for the first capture that separates them.
 */
export function LabelSummary({
  services,
  captureUuid,
  calls,
  silent,
  onPress,
  onMarkByEar,
}: {
  services: AppServices;
  captureUuid: string;
  /** The analyzer's detections — the same list the deck builds its cards from. */
  calls: DetectedSpan[];
  /** Confirmed to hold no calls, so there is nothing here to work through. */
  silent?: boolean;
  onPress: () => void;
  /** Jump to mark-by-ear on this screen, for the secondary link. */
  onMarkByEar: () => void;
}) {
  const [cards, setCards] = useState<ReturnType<typeof buildLabelCards>>([]);

  const refresh = useCallback(async () => {
    setCards(buildLabelCards(calls, await services.labels.forCapture(captureUuid)));
  }, [calls, captureUuid, services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const decided = countDecided(cards);
  const total = cards.length;
  const done = total > 0 && decided >= total;

  const nothingToOpen = total === 0;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.row}>
        <Text style={styles.title}>Label calls</Text>
        <Text style={[styles.count, done && styles.done]}>
          {silent && nothingToOpen ? "marked silent" : nothingToOpen ? "none found" : `${decided} of ${total}`}
        </Text>
      </View>

      {total > 0 ? (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${(decided / total) * 100}%` }]} />
        </View>
      ) : null}

      <Text style={styles.hint}>
        {silent && nothingToOpen
          ? "Marked as holding no calls. Open to change that, or to say what was happening anyway."
          : nothingToOpen
            ? "The analyzer found nothing. Open to mark it silent, or say what was seen nearby."
            : done
              ? "Every call decided. Open to review or add one the analyzer missed."
              : "One call at a time: play it, say what it was, say what was happening."}
      </Text>

      {/* Secondary, because marking a call the analyzer missed needs the
          waveform and the playhead, which are on this screen and not in the
          deck. */}
      <Pressable
        onPress={onMarkByEar}
        accessibilityRole="button"
        style={({ pressed }) => [pressed && styles.pressed]}
      >
        <Text style={styles.secondary}>Or mark a call by ear ↓</Text>
      </Pressable>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: 14, fontWeight: "600" },
  count: { color: colors.textMuted, fontSize: 13, fontVariant: ["tabular-nums"] },
  done: { color: colors.good, fontWeight: "700" },
  track: {
    height: 4,
    backgroundColor: colors.surfaceDeep,
    borderRadius: 2,
    overflow: "hidden",
  },
  fill: { height: 4, backgroundColor: colors.accent },
  hint: { color: colors.textFaint, fontSize: 12 },
  secondary: { color: colors.accent, fontSize: 12, fontWeight: "600" },
  pressed: { opacity: 0.7 },
});
