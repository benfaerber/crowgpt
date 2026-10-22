import { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { REGION_GROUPS, searchRegions } from "../../domain/regions";
import { colors, radius, spacing } from "../theme";

/**
 * Pick a region from a list rather than typing one.
 *
 * This string is a grouping key — it decides which captures count as the same
 * population — and free text produces "Utah", "utah", "UT" and "Utah, USA" as
 * four different places inside a month, which nothing downstream can undo.
 *
 * A search box on top of the list because eighty-odd entries is too many to
 * scroll and too few to justify anything cleverer. Searching matches the
 * country as well as the region: someone who knows they are in Germany does not
 * necessarily know how this list spells their Bundesland.
 */
export function RegionPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (region: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const matches = useMemo(() => searchRegions(query), [query]);

  return (
    <>
      <Pressable
        onPress={() => {
          setQuery("");
          setOpen(true);
        }}
        accessibilityRole="button"
        style={({ pressed }) => [styles.field, pressed && styles.pressed]}
      >
        <Text style={value ? styles.value : styles.empty}>
          {value || "Choose your region"}
        </Text>
        <Text style={styles.chevron}>▾</Text>
      </Pressable>

      <Modal visible={open} animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={styles.sheet}>
          <View style={styles.head}>
            <Text style={styles.title}>Your region</Text>
            <Pressable onPress={() => setOpen(false)} hitSlop={12}>
              <Text style={styles.close}>Done</Text>
            </Pressable>
          </View>

          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search states, provinces, countries"
            placeholderTextColor={colors.textFaint}
            style={styles.search}
            autoCorrect={false}
            autoFocus
          />

          <ScrollView contentContainerStyle={styles.list}>
            {/* Cleared explicitly rather than by deleting text, since there is
                no text to delete. Someone who would rather say nothing about
                where they are should not have to fight the picker. */}
            <Pressable
              onPress={() => {
                onChange("");
                setOpen(false);
              }}
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <Text style={styles.rowText}>Prefer not to say</Text>
            </Pressable>

            {matches.length === 0 ? (
              <Text style={styles.hint}>
                Nothing matches. Regions outside this list are still recorded when
                a capture has a GPS fix of its own.
              </Text>
            ) : (
              matches.map(({ key, group }) => (
                <Pressable
                  key={key}
                  onPress={() => {
                    onChange(key);
                    setOpen(false);
                  }}
                  style={({ pressed }) => [
                    styles.row,
                    key === value && styles.rowOn,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={[styles.rowText, key === value && styles.rowTextOn]}>
                    {key === value ? "● " : ""}
                    {key.replace(`, ${group.country}`, "")}
                  </Text>
                  <Text style={styles.country}>{group.countryName}</Text>
                </Pressable>
              ))
            )}
          </ScrollView>
        </View>
      </Modal>
    </>
  );
}

/** Countries offered, for a hint under the field. */
export const REGION_COUNTRIES = REGION_GROUPS.map((group) => group.countryName).join(", ");

const styles = StyleSheet.create({
  field: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  value: { color: colors.text, fontSize: 14 },
  empty: { color: colors.textFaint, fontSize: 14 },
  chevron: { color: colors.textMuted, fontSize: 12 },
  pressed: { opacity: 0.6 },
  sheet: { flex: 1, backgroundColor: colors.background, paddingTop: 56 },
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  title: { color: colors.text, fontSize: 20, fontWeight: "700" },
  close: { color: colors.accent, fontSize: 16, fontWeight: "600" },
  search: {
    backgroundColor: colors.surface,
    color: colors.text,
    borderRadius: radius.sm,
    marginHorizontal: spacing.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  list: { padding: spacing.lg, gap: spacing.xs },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  rowOn: { borderWidth: 1, borderColor: colors.accent },
  rowText: { color: colors.text, fontSize: 14 },
  rowTextOn: { fontWeight: "700" },
  country: { color: colors.textFaint, fontSize: 11 },
  hint: { color: colors.textFaint, fontSize: 12 },
});
