import { Pressable, StyleSheet, Switch, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import { ContextTagger } from "./ContextTagger";
import { colors, radius, spacing } from "../theme";

/**
 * "I listened to all of this and the crows said nothing."
 *
 * The corpus can already say what was happening when a crow called. It cannot
 * say how often the same thing happened and the crow said *nothing* — and until
 * it can, "crows alarm at dogs" is a count of the times somebody pressed record
 * rather than a finding. These recordings are the denominator.
 *
 * Only worth marking deliberately, which is why it is a switch and not a
 * default: an unreviewed capture and a genuinely quiet one look identical, and
 * the whole value here is in telling them apart. Marking one you haven't
 * listened to is worse than leaving it alone.
 *
 * Marking it opens capture-level context tagging — the one place that is
 * allowed, since with no calls there is nothing to miscredit a situation to.
 * That is what records "peanuts down, three crows watching, nobody spoke".
 */
export function SilenceMark({
  services,
  captureUuid,
  silentConfirmedAt,
  hasLabels,
  onChange,
}: {
  services: AppServices;
  captureUuid: string;
  silentConfirmedAt?: string;
  /** Calls already marked on this recording — silence would contradict them. */
  hasLabels: boolean;
  onChange: (silent: boolean) => void;
}) {
  const silent = silentConfirmedAt !== undefined;

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={styles.text}>
          <Text style={styles.label}>No crow calls in this one</Text>
          <Text style={styles.hint}>
            {hasLabels
              ? "This recording has marked calls, so it isn't silent."
              : silent
                ? "Counted as a control: something happened and nobody called."
                : "Only tick this after listening to the whole thing."}
          </Text>
        </View>
        <Switch
          value={silent}
          disabled={hasLabels}
          onValueChange={onChange}
          trackColor={{ true: colors.accent, false: colors.border }}
        />
      </View>

      {silent ? (
        <View style={styles.tagger}>
          <Text style={styles.section}>What was happening anyway</Text>
          {/* No labelUuid: there is no call to hang this on, which is exactly
              the condition that makes capture-level tagging honest here. */}
          <ContextTagger services={services} captureUuid={captureUuid} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.md,
    gap: spacing.sm,
  },
  text: { flex: 1, gap: 2 },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 11 },
  tagger: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  section: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
});
