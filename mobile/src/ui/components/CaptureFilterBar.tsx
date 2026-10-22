import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  RANGE_LABELS,
  type CaptureView,
  type DateRange,
} from "../../domain/captureFilters";
import { colors, radius, spacing } from "../theme";

const RANGES: DateRange[] = ["all", "today", "week", "month"];

/**
 * Date range, sort order and the keep flag, in one row.
 *
 * The list grows by a handful of recordings a day and most of the corpus is
 * seeded clips, so this morning's work is several screens down by the
 * afternoon. Nothing here deletes or hides anything permanently — every control
 * is a view, and the banner below the bar always says how much is being held
 * back.
 *
 * Horizontally scrollable rather than wrapped: a field app is used one-handed
 * and a bar that reflows to two rows moves the record button down the screen.
 */
export function CaptureFilterBar({
  view,
  keptCount,
  waitingCount,
  onChange,
}: {
  view: CaptureView;
  /** How many captures are marked real, for the star pill. */
  keptCount: number;
  /** Kept recordings nobody has labelled or waved past yet. */
  waitingCount: number;
  onChange: (view: CaptureView) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.bar}
    >
      {RANGES.map((range) => {
        const on = view.range === range;
        return (
          <Pressable
            key={range}
            onPress={() => onChange({ ...view, range })}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            style={({ pressed }) => [styles.pill, on && styles.pillOn, pressed && styles.pressed]}
          >
            <Text style={[styles.pillText, on && styles.pillTextOn]}>
              {RANGE_LABELS[range]}
            </Text>
          </Pressable>
        );
      })}

      <View style={styles.divider} />

      {/* One control with two states rather than two pills: the list is always
          sorted one way or the other, so a pair would imply it could be neither. */}
      <Pressable
        onPress={() =>
          onChange({ ...view, order: view.order === "newest" ? "oldest" : "newest" })
        }
        accessibilityRole="button"
        accessibilityLabel={
          view.order === "newest" ? "Sorted newest first" : "Sorted oldest first"
        }
        style={({ pressed }) => [styles.pill, pressed && styles.pressed]}
      >
        <Text style={styles.pillText}>
          {view.order === "newest" ? "↓ Newest" : "↑ Oldest"}
        </Text>
      </Pressable>

      {/* Last, and it wears a count rather than a label, because the number IS
          the reason to press it — a bare "To label" says nothing about whether
          it is worth opening. Hidden entirely at zero: a queue pill that is
          always there and always empty is the thing people stop seeing. */}
      {waitingCount > 0 || view.unlabelledOnly ? (
        <Pressable
          onPress={() => onChange({ ...view, unlabelledOnly: !view.unlabelledOnly })}
          accessibilityRole="button"
          accessibilityLabel={`${waitingCount} kept recordings waiting to be labelled`}
          accessibilityState={{ selected: view.unlabelledOnly }}
          style={({ pressed }) => [
            styles.pill,
            view.unlabelledOnly && styles.pillQueue,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.pillText, view.unlabelledOnly && styles.pillTextQueue]}>
            {`To label ${waitingCount}`}
          </Text>
        </Pressable>
      ) : null}

      <Pressable
        onPress={() => onChange({ ...view, keptOnly: !view.keptOnly })}
        accessibilityRole="button"
        accessibilityLabel={view.keptOnly ? "Showing kept only" : "Showing all captures"}
        accessibilityState={{ selected: view.keptOnly }}
        style={({ pressed }) => [
          styles.pill,
          view.keptOnly && styles.pillKept,
          pressed && styles.pressed,
        ]}
      >
        <Text style={[styles.pillText, view.keptOnly && styles.pillTextKept]}>
          {view.keptOnly ? `★ ${keptCount}` : `☆ ${keptCount}`}
        </Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  pillQueue: { borderColor: colors.accent, backgroundColor: colors.surfaceDeep },
  pillTextQueue: { color: colors.accent },
  bar: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingVertical: 2 },
  pill: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
  },
  pillOn: { borderColor: colors.accent, backgroundColor: colors.surfaceDeep },
  pillKept: { borderColor: colors.warn },
  pillText: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  pillTextOn: { color: colors.accent },
  pillTextKept: { color: colors.warn },
  divider: { width: 1, height: 16, backgroundColor: colors.border, marginHorizontal: 2 },
  pressed: { opacity: 0.6 },
});
