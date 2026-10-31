import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import type { AppServices, Settings } from "../app/AppServices";
import { enrollmentProblem } from "../domain/firstRun";
import { colors, pageEnd, radius, spacing } from "./theme";

/**
 * The first thing a fresh install shows: join the fleet, or not yet.
 *
 * Three fields and a button, deliberately not the whole of Settings. The token
 * is the one thing without which nothing syncs; the name is what the captures
 * are filed under; the claim code is how a second phone becomes the same
 * person rather than a stranger. The server address is shown, not edited —
 * it defaults to the hosted field server, and anyone running their own
 * changes it in Settings afterwards.
 */
export function EnrollScreen({
  services,
  onChange,
  onEnrolled,
  onSkip,
}: {
  services: AppServices;
  onChange: (settings: Settings) => void;
  onEnrolled: () => void;
  onSkip: () => void;
}) {
  const [token, setToken] = useState(services.settings.enrollToken);
  const [name, setName] = useState(services.settings.contributorName);
  const [claimCode, setClaimCode] = useState(services.settings.claimCode);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | undefined>();

  const enroll = async () => {
    const problem = enrollmentProblem(token);
    if (problem) {
      setMessage(problem);
      return;
    }
    setBusy(true);
    setMessage(undefined);
    try {
      onChange({
        ...services.settings,
        enrollToken: token.trim(),
        contributorName: name.trim(),
        claimCode: claimCode.trim(),
      });
      const identity = await services.enroll();
      setMessage(`Enrolled as ${identity.contributorName}.`);
      onEnrolled();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Join the fleet</Text>
        <Text style={styles.lede}>
          Recordings sync to {services.settings.fieldServerUrl}. Enrolling once is
          what lets this phone send them.
        </Text>

        <View style={styles.group}>
          <Text style={styles.label}>Enrollment token</Text>
          <TextInput
            style={styles.input}
            value={token}
            onChangeText={setToken}
            autoCapitalize="none"
            autoCorrect={false}
            autoFocus
            placeholder="From Ben"
            placeholderTextColor={colors.textFaint}
          />
          <Text style={styles.hint}>
            Needed exactly once. It is not shown again after this phone has enrolled.
          </Text>
        </View>

        <View style={styles.group}>
          <Text style={styles.label}>Your name</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="Shown against your captures"
            placeholderTextColor={colors.textFaint}
          />
        </View>

        <View style={styles.group}>
          <Text style={styles.label}>Claim code (optional)</Text>
          <TextInput
            style={styles.input}
            value={claimCode}
            onChangeText={setClaimCode}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="If this is your second phone, or a reinstall"
            placeholderTextColor={colors.textFaint}
          />
          <Text style={styles.hint}>
            From your other phone&apos;s Settings, or minted for you. With it this
            phone is you and sees your captures; without it, it starts a new account.
          </Text>
        </View>

        {message ? <Text style={styles.message}>{message}</Text> : null}

        <Pressable
          onPress={() => void enroll()}
          disabled={busy}
          style={({ pressed }) => [
            styles.action,
            styles.actionPrimary,
            busy && styles.disabled,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.actionText}>{busy ? "Enrolling…" : "Enroll this phone"}</Text>
        </Pressable>

        <Pressable onPress={onSkip} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.skip}>Not now — record offline, enroll from Settings later</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  body: { paddingHorizontal: spacing.lg, paddingTop: 72, paddingBottom: pageEnd, gap: spacing.lg },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  lede: { color: colors.textMuted, fontSize: 14 },
  group: { gap: spacing.xs },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 12 },
  input: {
    backgroundColor: colors.surface,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 14,
  },
  message: { color: colors.textMuted, fontSize: 13 },
  action: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.6 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  skip: { color: colors.textMuted, fontSize: 13, textAlign: "center" },
});
