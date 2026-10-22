import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../theme";

/**
 * What the recordist was to these crows when this was recorded.
 *
 * The variable that flips the meaning of everything else on the tape. The same
 * caw from a bird that knows you feeds it and from one meeting you for the first
 * time are different recordings of different things, and nothing in the audio
 * distinguishes them — so it has to be said here or it is lost.
 *
 * Options come from the served vocabulary, not a hardcoded list: the phone and
 * the dashboard must agree about what "feeder" means, and the set is expected to
 * change without a rebuild.
 *
 * Collapsed until tapped, and never required. Most captures are made in a hurry,
 * and this is usually remembered back at the desk.
 */
export function ObserverRolePicker({
  roles,
  selected,
  onSelect,
}: {
  roles: { key: string; text: string }[];
  selected?: string;
  onSelect: (key: string | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  if (roles.length === 0) return null;
  const current = roles.find((role) => role.key === selected);

  return (
    <View style={styles.card}>
      <Pressable
        onPress={() => setOpen((was) => !was)}
        accessibilityRole="button"
        style={({ pressed }) => [styles.summary, pressed && styles.pressed]}
      >
        <Text style={styles.label}>They know me as</Text>
        <View style={styles.current}>
          {/* "Not said" rather than a default. Nobody answering is not the same
              claim as "stranger", and this field is only worth having if it can
              be trusted. */}
          <Text style={current ? styles.currentName : styles.currentNone}>
            {current ? current.text : "Not said"}
          </Text>
          <Text style={styles.chevron}>{open ? "▲" : "▼"}</Text>
        </View>
      </Pressable>

      {open && (
        <View style={styles.options}>
          <Pressable
            onPress={() => {
              onSelect(undefined);
              setOpen(false);
            }}
            style={({ pressed }) => [styles.option, pressed && styles.pressed]}
          >
            <Text style={selected ? styles.optionText : styles.optionTextActive}>
              Not said
            </Text>
          </Pressable>

          {roles.map((role) => (
            <Pressable
              key={role.key}
              onPress={() => {
                onSelect(role.key);
                setOpen(false);
              }}
              accessibilityRole="button"
              style={({ pressed }) => [styles.option, pressed && styles.pressed]}
            >
              <Text
                style={role.key === selected ? styles.optionTextActive : styles.optionText}
              >
                {role.text}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  summary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.md,
  },
  pressed: { opacity: 0.7 },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  current: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  currentName: { color: colors.text, fontSize: 14 },
  currentNone: { color: colors.textFaint, fontSize: 14 },
  chevron: { color: colors.textFaint, fontSize: 10 },
  options: { borderTopWidth: 1, borderTopColor: colors.border },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  optionText: { color: colors.textMuted, fontSize: 14 },
  optionTextActive: { color: colors.accent, fontSize: 14, fontWeight: "600" },
});
