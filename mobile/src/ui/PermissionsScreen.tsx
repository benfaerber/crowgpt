import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type {
  PermissionInfo,
  PermissionKey,
  PermissionsManager,
  PermissionState,
} from "../platform/Permissions";
import { colors, pageEnd, radius, spacing } from "./theme";

const STATE_LABELS: Record<PermissionState, string> = {
  granted: "Granted",
  undetermined: "Not asked",
  denied: "Refused",
  blocked: "Blocked",
};

const STATE_COLORS: Record<PermissionState, string> = {
  granted: colors.good,
  undetermined: colors.textMuted,
  denied: colors.warn,
  blocked: colors.bad,
};

/**
 * One place to see what the app has been granted and fix what it hasn't.
 *
 * Permission prompts otherwise appear scattered through the app at the moment
 * each feature is first used, which is exactly when someone is busy doing
 * something else and taps the wrong button. This exists so a refused permission
 * is discoverable and recoverable afterwards rather than a mystery about why
 * captures have no location.
 */
export function PermissionsScreen({
  permissions,
  onBack,
}: {
  permissions: PermissionsManager;
  onBack: () => void;
}) {
  const [entries, setEntries] = useState<PermissionInfo[]>([]);
  const [busy, setBusy] = useState<PermissionKey | null>(null);

  const refresh = useCallback(async () => {
    setEntries(await permissions.list());
  }, [permissions]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const request = useCallback(
    async (key: PermissionKey) => {
      setBusy(key);
      try {
        await permissions.request(key);
        await refresh();
      } finally {
        setBusy(null);
      }
    },
    [permissions, refresh],
  );

  const anythingBlocked = entries.some((entry) => entry.state === "blocked");

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>‹ Settings</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.title}>Permissions</Text>

        {entries.map((entry) => (
          <View key={entry.key} style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>
                {entry.title}
                {entry.essential ? " *" : ""}
              </Text>
              <View style={[styles.badge, { borderColor: STATE_COLORS[entry.state] }]}>
                <Text style={[styles.badgeText, { color: STATE_COLORS[entry.state] }]}>
                  {STATE_LABELS[entry.state]}
                </Text>
              </View>
            </View>

            <Text style={styles.why}>{entry.why}</Text>

            {entry.state === "granted" ? null : entry.state === "blocked" ? (
              <Pressable
                onPress={() => permissions.openSystemSettings()}
                style={({ pressed }) => [styles.action, pressed && styles.pressed]}
              >
                <Text style={styles.actionText}>Open system settings</Text>
              </Pressable>
            ) : (
              <Pressable
                onPress={() => request(entry.key)}
                disabled={busy === entry.key}
                style={({ pressed }) => [
                  styles.action,
                  styles.actionPrimary,
                  busy === entry.key && styles.disabled,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.actionText}>
                  {busy === entry.key ? "Asking…" : "Grant"}
                </Text>
              </Pressable>
            )}
          </View>
        ))}

        <Text style={styles.footnote}>* required for the app to work at all.</Text>

        {anythingBlocked ? (
          <Text style={styles.footnote}>
            A blocked permission can&apos;t be re-requested from inside the app — Android
            only allows it to be changed from system settings.
          </Text>
        ) : null}

        <Pressable
          onPress={refresh}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Re-check</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: spacing.sm },
  back: { color: colors.accent, fontSize: 16 },
  pressed: { opacity: 0.6 },
  body: { paddingHorizontal: spacing.lg, paddingBottom: pageEnd, gap: spacing.md },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cardTitle: { color: colors.text, fontSize: 16, fontWeight: "600" },
  badge: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  badgeText: { fontSize: 11, fontWeight: "700" },
  why: { color: colors.textMuted, fontSize: 13 },
  action: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.5 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  footnote: { color: colors.textFaint, fontSize: 12 },
});
