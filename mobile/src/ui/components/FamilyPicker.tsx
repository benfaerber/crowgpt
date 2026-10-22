import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { FamilyRecord } from "../../domain/families";
import { colors, radius, spacing } from "../theme";

/**
 * Assigns a capture to a family.
 *
 * Collapsed to a single row until tapped, because most captures are made in a
 * hurry and a family is optional — it should never stand between recording and
 * getting on with it.
 */
export function FamilyPicker({
  families,
  selectedUuid,
  onSelect,
  onCreateNew,
}: {
  families: FamilyRecord[];
  selectedUuid?: string;
  onSelect: (uuid: string | undefined) => void;
  onCreateNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = families.find((f) => f.uuid === selectedUuid);

  return (
    <View style={styles.card}>
      <Pressable
        onPress={() => setOpen((was) => !was)}
        style={({ pressed }) => [styles.summary, pressed && styles.pressed]}
      >
        <Text style={styles.label}>Family</Text>
        <View style={styles.current}>
          {selected ? (
            <View style={[styles.dot, { backgroundColor: selected.color, shadowColor: selected.color }]} />
          ) : null}
          <Text style={selected ? styles.currentName : styles.currentNone}>
            {selected ? selected.name : "None"}
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
            <Text style={selectedUuid ? styles.optionText : styles.optionTextActive}>None</Text>
          </Pressable>

          {families.map((family) => (
            <Pressable
              key={family.uuid}
              onPress={() => {
                onSelect(family.uuid);
                setOpen(false);
              }}
              style={({ pressed }) => [styles.option, pressed && styles.pressed]}
            >
              <View style={[styles.dot, { backgroundColor: family.color, shadowColor: family.color }]} />
              <Text
                style={family.uuid === selectedUuid ? styles.optionTextActive : styles.optionText}
              >
                {family.name}
              </Text>
            </Pressable>
          ))}

          <Pressable
            onPress={() => {
              setOpen(false);
              onCreateNew();
            }}
            style={({ pressed }) => [styles.option, styles.createOption, pressed && styles.pressed]}
          >
            <Text style={styles.createText}>+ New family…</Text>
          </Pressable>
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
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  current: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  currentName: { color: colors.text, fontSize: 14 },
  currentNone: { color: colors.textFaint, fontSize: 14 },
  chevron: { color: colors.textMuted, fontSize: 10 },
  options: { borderTopWidth: 1, borderTopColor: colors.border },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  createOption: { borderTopWidth: 1, borderTopColor: colors.border },
  optionText: { color: colors.textMuted, fontSize: 14 },
  optionTextActive: { color: colors.text, fontSize: 14, fontWeight: "700" },
  createText: { color: colors.accent, fontSize: 14, fontWeight: "700" },
  dot: { width: 12, height: 12, borderRadius: 6, shadowOpacity: 0.9, shadowRadius: 6, elevation: 4 },
  pressed: { opacity: 0.7 },
});
