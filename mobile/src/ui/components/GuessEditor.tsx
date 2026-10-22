import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "../theme";

/**
 * What you think was going on — "I guess they caw at a group of teenagers".
 *
 * Sits under the description because it is the natural next sentence, and is
 * deliberately a *separate field* rather than more of the same box. The
 * description records what happened; this records what you concluded from it,
 * and a corpus that cannot tell those apart is one where every finding is
 * already assumed somewhere in the data.
 *
 * Free text on purpose. A hypothesis you have to phrase in preset terms is one
 * you have already narrowed to what you expected — and the whole use of these
 * is the guesses nobody thought to make a preset for. Read a season of them and
 * the ones that keep recurring are the hypotheses worth designing a real test
 * for; the ones that stop recurring are the ones the data quietly refused.
 *
 * Never exported for training, never entered into the calls × context matrix.
 * The label says so, because a field that looks like ground truth will be
 * treated as ground truth.
 */
export function GuessEditor({
  value,
  onSave,
}: {
  value?: string;
  onSave: (guess: string) => Promise<unknown>;
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
      <View style={styles.row}>
        <Text style={styles.label}>What do you think it meant?</Text>
        <Text style={styles.tag}>a guess</Text>
      </View>

      <TextInput
        style={styles.input}
        value={draft}
        onChangeText={setDraft}
        onFocus={() => setEditing(true)}
        onBlur={() => setEditing(false)}
        placeholder="Why do you think they were calling?"
        placeholderTextColor={colors.textFaint}
        multiline
      />

      <Text style={styles.hint}>
        Your interpretation, not an observation. It stays out of the training data
        and the calls × context matrix, so being wrong costs nothing — and a guess
        that keeps recurring across recordings is one worth testing properly.
      </Text>

      {dirty ? (
        <Pressable
          onPress={save}
          disabled={saving}
          accessibilityRole="button"
          style={({ pressed }) => [styles.save, saving && styles.disabled, pressed && styles.pressed]}
        >
          <Text style={styles.saveText}>{saving ? "Saving…" : "Save guess"}</Text>
        </Pressable>
      ) : null}
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
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  tag: {
    color: colors.warn,
    borderColor: colors.warn,
    borderWidth: 1,
    borderRadius: radius.pill,
    fontSize: 10,
    fontWeight: "700",
    paddingHorizontal: spacing.sm,
    paddingVertical: 1,
  },
  input: {
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    color: colors.text,
    padding: spacing.sm,
    minHeight: 56,
    fontSize: 14,
  },
  hint: { color: colors.textFaint, fontSize: 11 },
  save: {
    backgroundColor: colors.accent,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.75 },
  saveText: { color: "#fff", fontSize: 13, fontWeight: "700" },
});
