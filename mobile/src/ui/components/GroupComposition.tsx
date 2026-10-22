import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../theme";

/** What a counter is called, and what it means when you can't tell. */
const ROWS = [
  { key: "adultCount", label: "Adults", hint: "full black eye, clean plumage" },
  { key: "juvenileCount", label: "Juveniles", hint: "blue-grey eye, pink gape, scruffy" },
  { key: "unagedCount", label: "Couldn't tell", hint: "seen, but too far to age" },
] as const;

export type CountField = (typeof ROWS)[number]["key"];

/**
 * How many birds were there, and how many were young.
 *
 * Not recoverable from audio: a fledgling begging among five birds and one adult
 * calling alone are different recordings, and nothing in a WAV says which.
 *
 * Three counters rather than two because the field notes demanded it. "3 crows
 * on 1 branch" states a number and no ages, and a schema of adults and juveniles
 * could only hold that by inventing one — so birds you saw but couldn't age get
 * their own row rather than being forced into a guess.
 *
 * Ageing a crow needs the eye and the gape, which means a few metres. At thirty
 * the honest row is the third one, and having it there makes using it easy.
 */
export function GroupComposition({
  adults,
  juveniles,
  unaged,
  onChange,
}: {
  adults?: number;
  juveniles?: number;
  unaged?: number;
  onChange: (field: CountField, value: number | undefined) => void;
}) {
  const values: Record<CountField, number | undefined> = {
    adultCount: adults,
    juvenileCount: juveniles,
    unagedCount: unaged,
  };
  const counted = ROWS.some((row) => values[row.key] !== undefined);
  const total = ROWS.reduce((sum, row) => sum + (values[row.key] ?? 0), 0);

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Text style={styles.label}>How many did you see?</Text>
        <Text style={counted ? styles.total : styles.totalNone}>
          {counted ? `${total} bird${total === 1 ? "" : "s"}` : "not counted"}
        </Text>
      </View>

      {ROWS.map((row) => {
        const value = values[row.key];
        return (
          <View key={row.key} style={styles.row}>
            <View style={styles.text}>
              <Text style={styles.name}>{row.label}</Text>
              <Text style={styles.hint}>{row.hint}</Text>
            </View>
            <Pressable
              // Stepping below zero clears it rather than sticking at 0, because
              // "none" and "I didn't count" are different claims and there has
              // to be a way back to the second one.
              onPress={() =>
                onChange(row.key, value === undefined || value === 0 ? undefined : value - 1)
              }
              disabled={value === undefined}
              accessibilityRole="button"
              accessibilityLabel={`One fewer ${row.label}`}
              style={({ pressed }) => [
                styles.step,
                value === undefined && styles.stepOff,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.stepText}>−</Text>
            </Pressable>
            <Text style={value === undefined ? styles.countNone : styles.count}>
              {value ?? "–"}
            </Text>
            <Pressable
              onPress={() => onChange(row.key, (value ?? 0) + 1)}
              accessibilityRole="button"
              accessibilityLabel={`One more ${row.label}`}
              style={({ pressed }) => [styles.step, pressed && styles.pressed]}
            >
              <Text style={styles.stepText}>+</Text>
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  head: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between" },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  total: { color: colors.text, fontSize: 12, fontWeight: "600" },
  totalNone: { color: colors.textFaint, fontSize: 12 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  text: { flex: 1, gap: 1 },
  name: { color: colors.text, fontSize: 14 },
  hint: { color: colors.textFaint, fontSize: 11 },
  step: {
    width: 34,
    alignItems: "center",
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceDeep,
  },
  stepOff: { opacity: 0.3 },
  pressed: { opacity: 0.6 },
  stepText: { color: colors.text, fontSize: 16, fontWeight: "700" },
  count: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
    width: 24,
    textAlign: "center",
    fontVariant: ["tabular-nums"],
  },
  countNone: {
    color: colors.textFaint,
    fontSize: 15,
    width: 24,
    textAlign: "center",
  },
});
