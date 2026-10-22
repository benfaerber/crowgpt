import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "../theme";

/**
 * The prose half of the ground truth.
 *
 * Deliberately unconstrained: presets are what train the model, and this is for
 * everything a preset can't hold yet — what the bird was doing, what it was
 * reacting to, why a prediction looks wrong. Which situations keep recurring in
 * here is how the preset vocabulary earns its next entry.
 */
export function DescriptionEditor({
  value,
  pendingSync,
  onSave,
}: {
  value?: string;
  /** True when the saved text hasn't reached the server yet. */
  pendingSync: boolean;
  onSave: (body: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  // Adopt the stored text when it changes underneath us — unless the user is
  // mid-edit, where overwriting what they are typing would be maddening.
  useEffect(() => {
    if (!editing) setDraft(value ?? "");
  }, [value, editing]);

  const dirty = draft.trim() !== (value ?? "").trim();

  const save = async () => {
    setSaving(true);
    try {
      await onSave(draft.trim());
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>Description</Text>
        {value && pendingSync ? <Text style={styles.pending}>not yet synced</Text> : null}
      </View>

      <TextInput
        style={styles.input}
        value={draft}
        onChangeText={setDraft}
        onFocus={() => setEditing(true)}
        multiline
        textAlignVertical="top"
        placeholder="What was happening? Who was calling, at what, and what followed."
        placeholderTextColor={colors.textFaint}
      />

      {dirty && (
        <View style={styles.actions}>
          <Pressable
            onPress={() => {
              setDraft(value ?? "");
              setEditing(false);
            }}
            style={({ pressed }) => [styles.action, pressed && styles.pressed]}
          >
            <Text style={styles.actionText}>Cancel</Text>
          </Pressable>
          <Pressable
            onPress={save}
            disabled={saving}
            style={({ pressed }) => [
              styles.action,
              styles.actionPrimary,
              saving && styles.disabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>{saving ? "Saving…" : "Save"}</Text>
          </Pressable>
        </View>
      )}

      <Text style={styles.hint}>
        Kept on the phone and uploaded with the capture on the next sync.
      </Text>
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
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: 16, fontWeight: "700" },
  pending: { color: colors.warn, fontSize: 11, fontWeight: "600" },
  input: {
    backgroundColor: colors.surfaceDeep,
    color: colors.text,
    borderRadius: radius.sm,
    padding: spacing.md,
    fontSize: 14,
    minHeight: 96,
  },
  actions: { flexDirection: "row", gap: spacing.sm },
  action: {
    flex: 1,
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.75 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 11 },
});
