import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import RawAudio, {
  type CueOutputState,
  type DisconnectCueOutcome,
} from "../../modules/raw-audio";
import { colors, pageEnd, radius, spacing } from "./theme";

/**
 * Everything the app says out loud, and why it might not be saying it.
 *
 * The cues are the only channel a phone in a bag has, and they are the hardest
 * part of this app to check: the failure is a sound that did not happen, in a
 * pocket, minutes after the screen went off. The spoken phrase is a bundled
 * recording now — it cannot be missing or rendered silent — so "it says
 * nothing" has two causes left: no earbuds paired, or a player that failed at
 * the moment the route was torn down, which the disconnect log line now
 * describes (said / cueRoute / cueFocus).
 *
 * So this screen leads with facts rather than buttons. THE FIRST ROW EXPLAINS
 * MOST SILENCES ON ITS OWN: every cue this app plays is deliberately held back
 * from the phone's own speaker, because a sound out loud lands in the recording.
 * With nothing paired, every cue is a vibration — including the ones being
 * tested here.
 */

const OUTCOME: Record<DisconnectCueOutcome, string> = {
  words: "Said the words.",
  tone: "Played the failure tone — the player refused to start the recording.",
  buzz: "Vibrated only, because nothing is connected to hear it with.",
};

export function CueDiagnosticsScreen({ onBack }: { onBack: () => void }) {
  const [state, setState] = useState<CueOutputState | null>(null);
  const [outcome, setOutcome] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  const refresh = useCallback(async () => {
    try {
      setState(await RawAudio.cueOutputState());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const say = async (throughSpeaker: boolean) => {
    setOutcome("Playing…");
    setError(undefined);
    try {
      const said = await RawAudio.testDisconnectCue(throughSpeaker);
      setOutcome(OUTCOME[said]);
      await refresh();
    } catch (failure) {
      setOutcome(undefined);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const tone = async (kind: "started" | "stopped" | "failed") => {
    setError(undefined);
    try {
      await RawAudio.playCue(kind);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const silentByDesign = state?.bluetoothOutput === false;

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable onPress={onBack} accessibilityRole="button">
          <Text style={styles.back}>‹ Diagnostics</Text>
        </Pressable>
        <Text style={styles.title}>Audio cues</Text>

        <Text style={styles.intro}>
          The tones, the heartbeat and the spoken “microphone disconnected”. Every
          one of them goes to connected earbuds and never to the phone’s own
          speaker, because a sound out loud lands in the recording.
        </Text>

        <View style={styles.card}>
          <Row
            label="Bluetooth output"
            value={
              state === null
                ? "…"
                : state.bluetoothOutput
                  ? "connected"
                  : "none connected"
            }
            good={state?.bluetoothOutput}
          />
        </View>

        {silentByDesign ? (
          <Text style={styles.warn}>
            Nothing is paired, so every cue below is a vibration and no test on
            this screen can make a sound. This is the app behaving as designed and
            it is the most likely reason a cue seemed dead. Connect the earbuds,
            or use the speaker test, which lifts the rule on purpose.
          </Text>
        ) : null}

        <Pressable
          onPress={() => say(false)}
          style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
        >
          <Text style={styles.buttonText}>Play it as it would in the field</Text>
        </Pressable>
        <Text style={styles.hint}>
          Exactly what happens when the external mic comes off mid-session — same
          code, same rule about the speaker.
        </Text>

        <Pressable
          onPress={() => say(true)}
          style={({ pressed }) => [
            styles.button,
            styles.buttonSecondary,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.buttonText}>Play the words through the speaker</Text>
        </Pressable>
        <Text style={styles.hint}>
          The same phrase with the speaker rule lifted, so the words can be heard
          on a desk with nothing paired. Never happens in the field.
        </Text>

        {outcome ? <Text style={styles.outcome}>{outcome}</Text> : null}

        <View style={styles.tones}>
          {(["started", "stopped", "failed"] as const).map((kind) => (
            <Pressable
              key={kind}
              onPress={() => tone(kind)}
              style={({ pressed }) => [styles.tone, pressed && styles.buttonPressed]}
            >
              <Text style={styles.toneText}>{kind}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.hint}>
          The three confirmation tones a capture makes. Worth hearing back to back
          once: told apart in a pocket they have to be, and the failure tone is
          also what the disconnect cue falls back to.
        </Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}
      </ScrollView>
    </View>
  );
}

function Row({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, good === true && styles.good, good === false && styles.bad]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingTop: 64, gap: spacing.md, paddingBottom: pageEnd },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  back: { color: colors.accent, fontSize: 16 },
  intro: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.xs, gap: spacing.md },
  rowLabel: { color: colors.textMuted, fontSize: 14 },
  rowValue: { color: colors.text, fontSize: 14, fontWeight: "600", flexShrink: 1, textAlign: "right" },
  good: { color: colors.good },
  bad: { color: colors.bad },
  warn: { color: colors.warn, fontSize: 13, lineHeight: 19 },
  error: { color: colors.bad, fontSize: 13 },
  outcome: { color: colors.text, fontSize: 14, fontWeight: "600" },
  button: {
    backgroundColor: colors.accent,
    paddingVertical: 16,
    borderRadius: radius.md,
    alignItems: "center",
  },
  buttonSecondary: { backgroundColor: colors.border },
  buttonPressed: { opacity: 0.75 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 12, lineHeight: 17 },
  tones: { flexDirection: "row", gap: spacing.sm },
  tone: {
    flex: 1,
    backgroundColor: colors.surfaceDeep,
    paddingVertical: 12,
    borderRadius: radius.sm,
    alignItems: "center",
  },
  toneText: { color: colors.text, fontSize: 13, fontWeight: "600" },
});
