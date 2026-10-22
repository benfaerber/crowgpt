import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "../theme";

/**
 * What the recordist calls this capture.
 *
 * Never auto-filled. A name the app invented would be a label nobody chose, and
 * a list that looks named while still being unsearchable is worse than one that
 * admits it is a list of timestamps.
 *
 * Commits on blur, like the settings fields: saving per keystroke would mark the
 * capture dirty on every character and queue a sync for each one.
 */
export function NameEditor({
  value,
  onSave,
}: {
  value?: string;
  onSave: (name: string) => void | Promise<void>;
}) {
  const [draft, setDraft] = useState(value ?? "");

  // The capture can change under us — deleting one, or picking another from the
  // list, reuses this component.
  useEffect(() => setDraft(value ?? ""), [value]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed === (value ?? "").trim()) return;
    void onSave(trimmed);
  };

  return (
    <View style={styles.card}>
      <Text style={styles.label}>Name</Text>
      <TextInput
        style={styles.input}
        value={draft}
        onChangeText={setDraft}
        onEndEditing={commit}
        onBlur={commit}
        placeholder="e.g. Edgar on the wire"
        placeholderTextColor={colors.textFaint}
        returnKeyType="done"
        onSubmitEditing={commit}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  input: {
    backgroundColor: colors.surfaceDeep,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
});
