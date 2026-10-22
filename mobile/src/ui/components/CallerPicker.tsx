import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import type { LabelRecord } from "../../domain/labels";
import { colors, radius, spacing } from "../theme";

/**
 * Which bird made this call.
 *
 * The only field on a label that nobody can fill in afterwards. Experiment 0017
 * established the audio does not carry the caller — five crows in one recording
 * produce the cluster structure one crow produces — so an attribution not made
 * while the bird is in view is not delayed, it is gone. That is why it sits on
 * the card rather than in a review screen.
 *
 * Nothing is preselected and there is no "unknown" button. An unset caller
 * already means nobody looked, and offering a button that says so would collect
 * taps rather than observations — the distinction between "I did not see" and
 * "there was nobody" is the one thing this field must not blur. Tapping the
 * chosen role again clears it, which is the undo.
 */
export function CallerPicker({
  services,
  label,
  onChanged,
}: {
  services: AppServices;
  label: LabelRecord;
  onChanged: () => void;
}) {
  const roles = services.config.caller_roles ?? [];
  const [saving, setSaving] = useState(false);
  const chosen = label.callerRole;

  // An older server has none of these, and a phone that invented some would put
  // keys in the corpus it has never heard of.
  if (roles.length === 0) return null;

  async function choose(key: string) {
    const next = chosen === key ? undefined : key;
    setSaving(true);
    try {
      await services.setLabelCaller(label, next);
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.callerBlock}>
      <Text style={styles.callerHeading}>Which bird called?</Text>
      <Text style={styles.callerHint}>
        Only if you saw it. Leave blank if you did not.
      </Text>
      <View style={styles.choices}>
        {roles.map((role) => {
          const active = chosen === role.key;
          return (
            <Pressable
              key={role.key}
              disabled={saving}
              onPress={() => choose(role.key)}
              style={({ pressed }) => [
                styles.callerChoice,
                active && styles.callerChoiceOn,
                pressed && styles.pressed,
              ]}
            >
              <Text
                style={[styles.callerChoiceText, active && styles.choiceTextOn]}
              >
                {active ? "✓ " : ""}
                {role.text}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Set apart from the call-type buttons above rather than continuing them.
  // They are different questions — what was said, and who said it — and a
  // recordist scanning one row of look-alike buttons would answer both as one.
  callerBlock: { marginTop: spacing.lg },
  callerHeading: { color: colors.text, fontSize: 14, fontWeight: "600" },
  callerHint: {
    color: colors.textMuted,
    fontSize: 12,
    marginTop: 2,
    marginBottom: spacing.sm,
  },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  // Quieter than a call type: this is optional and usually left blank, and a
  // row of buttons as loud as the ones above would read as a second required
  // step rather than an offer.
  callerChoice: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  callerChoiceOn: { borderColor: colors.accent, backgroundColor: `${colors.accent}22` },
  callerChoiceText: { color: colors.textMuted, fontSize: 13 },
  choiceTextOn: { fontWeight: "800" },
  pressed: { opacity: 0.7 },
});
