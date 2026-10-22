import { Pressable, StyleSheet, Text, View } from "react-native";

import { DISTANCE_BANDS } from "../../domain/distance";
import { colors, radius, spacing } from "../theme";

/**
 * How far away the bird was, in one tap.
 *
 * Worth the tap because nothing else can recover it. Two recordists on two
 * continents produce audio that differs in signal-to-noise and spectral tilt
 * purely from how close they got, and without this every difference between
 * their corpora is also a difference in distance — which makes the comparison
 * unreadable rather than merely noisy.
 */
export function DistancePicker({
  value,
  onChange,
}: {
  value?: string;
  onChange: (band: string | undefined) => void;
}) {
  const chosen = DISTANCE_BANDS.find((band) => band.key === value);

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.label}>How far away?</Text>
        <Text style={chosen ? styles.hint : styles.hintFaint}>
          {chosen ? chosen.hint : "not said"}
        </Text>
      </View>
      <View style={styles.bands}>
        {DISTANCE_BANDS.map((band) => {
          const on = band.key === value;
          return (
            <Pressable
              key={band.key}
              // Tapping the chosen one clears it: a guess you no longer stand
              // behind should be removable, and "not said" is a real answer.
              onPress={() => onChange(on ? undefined : band.key)}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={({ pressed }) => [
                styles.band,
                on && styles.bandOn,
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.bandText, on && styles.bandTextOn]}>{band.label}</Text>
            </Pressable>
          );
        })}
      </View>
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
  row: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between" },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  hint: { color: colors.textMuted, fontSize: 11 },
  hintFaint: { color: colors.textFaint, fontSize: 11 },
  bands: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  band: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
  },
  bandOn: { borderColor: colors.accent, backgroundColor: colors.surfaceDeep },
  bandText: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  bandTextOn: { color: colors.accent },
  pressed: { opacity: 0.6 },
});
