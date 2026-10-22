import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AppState,
  type AppStateStatus,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { AppServices } from "../app/AppServices";
import { log } from "../app/Log";
import RawAudio from "../../modules/raw-audio";
import { colors, pageEnd, radius, spacing } from "./theme";

/**
 * Whether the earbud button still works when nobody is looking.
 *
 * Mic diagnostics answers "what did the microphone give us", which is a
 * question about one recording. This one answers "did the press arrive", which
 * is a question about a walk — and it cannot be answered on screen, because the
 * failure only happens once the screen is off. So the screen's real job is to
 * still be here afterwards: it holds the taps it saw and what the app was doing
 * at the time, and you read it when you come back.
 *
 * Written after a press in the field did nothing and there was no way to say
 * which half had failed — the button never reaching the app, or the app
 * receiving it and doing nothing with it. Those have different fixes and the
 * recordist could not tell them apart.
 */

type Tap = {
  at: number;
  keyCode?: number;
  /** What the app was doing when it arrived — the whole point of the log. */
  appState: AppStateStatus;
};

function clockTime(at: number): string {
  return new Date(at).toLocaleTimeString(undefined, { hour12: false });
}

export function HeadsetDiagnosticsScreen({
  services,
  onBack,
}: {
  services: AppServices;
  onBack: () => void;
}) {
  const settings = services.settings;
  const [taps, setTaps] = useState<Tap[]>([]);
  const [held, setHeld] = useState(false);
  const [bluetooth, setBluetooth] = useState<boolean | null>(null);
  const [appState, setAppState] = useState<AppStateStatus>(AppState.currentState);
  const [otherAudio, setOtherAudio] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | undefined>();

  // The setting's own claim is asserted at startup and on change, so leaving
  // this screen must put the button back the way the recordist set it rather
  // than the way this screen left it.
  const restoreOnLeave = useRef(settings.headsetTrigger);

  useEffect(() => {
    const subscription = RawAudio.addMediaButtonListener((event) => {
      setTaps((previous) => [
        { at: Date.now(), keyCode: event.keyCode, appState: AppState.currentState },
        ...previous,
      ].slice(0, 50));
    });
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", setAppState);
    return () => subscription.remove();
  }, []);

  const refreshBluetooth = useCallback(() => {
    RawAudio.hasBluetoothOutput().then(setBluetooth).catch(() => setBluetooth(null));
  }, []);

  useEffect(() => {
    refreshBluetooth();
  }, [refreshBluetooth, appState]);

  // Polled rather than read once: the whole question is whether something is
  // playing *at the moment you press*, and that changes under you.
  useEffect(() => {
    const read = () => {
      try {
        setOtherAudio(RawAudio.isOtherAudioPlaying());
      } catch {
        setOtherAudio(null);
      }
    };
    read();
    const timer = setInterval(read, 2000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const wanted = restoreOnLeave.current;
    return () => {
      // Logged rather than swallowed — on the diagnostics screen of all
      // places, a trigger left in the wrong state on the way out is exactly
      // the kind of fact this screen exists to surface.
      if (wanted) {
        void RawAudio.acquireMediaButton().catch((failure) =>
          log.warn("recorder", "could not re-arm the trigger on leaving diagnostics",
                   failure));
      } else {
        void RawAudio.releaseMediaButton().catch((failure) =>
          log.warn("recorder", "could not release the trigger on leaving diagnostics",
                   failure));
      }
    };
  }, []);

  const hold = useCallback(async () => {
    try {
      await RawAudio.acquireMediaButton();
      setHeld(true);
      setMessage("Holding the button. Tap an earbud.");
    } catch (error) {
      setMessage(`Could not take the button: ${String(error)}`);
    }
  }, []);

  const release = useCallback(async () => {
    try {
      await RawAudio.releaseMediaButton();
      setHeld(false);
      setMessage("Released. Other apps have the button back.");
    } catch (error) {
      setMessage(`Could not release: ${String(error)}`);
    }
  }, []);

  const cue = useCallback(async () => {
    try {
      await RawAudio.playCue("started");
      setMessage("Played the started tone.");
    } catch (error) {
      setMessage(`Cue failed: ${String(error)}`);
    }
  }, []);

  const backgroundTaps = taps.filter((tap) => tap.appState !== "active").length;

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable onPress={onBack} accessibilityRole="button">
          <Text style={styles.back}>‹ Settings</Text>
        </Pressable>
        <Text style={styles.title}>Earbud button diagnostics</Text>

        <Text style={styles.intro}>
          Hold the button, put the phone in your pocket with the screen off, tap
          an earbud a few times, then come back here. Every press that reached
          the app is listed below with what the app was doing when it landed. An
          empty list after tapping means the press never arrived at all, which is
          a different fault from one that arrived and did nothing.
        </Text>

        <View style={styles.card}>
          <Row
            label="Earbud trigger setting"
            value={settings.headsetTrigger ? "on" : "off"}
            good={settings.headsetTrigger}
          />
          <Row
            label="Pocket listening"
            value={settings.backgroundListening ? "on" : "off"}
            good={settings.backgroundListening}
          />
          <Row
            label="Bluetooth output"
            value={
              bluetooth === null ? "unknown" : bluetooth ? "connected" : "none connected"
            }
            good={bluetooth === true}
          />
          {/* The one that predicts failure. Android hands the button to
              whichever app played most recently, so anything still playing is
              something still winning. */}
          <Row
            label="Another app playing"
            value={otherAudio === null ? "unknown" : otherAudio ? "yes — contested" : "no"}
            good={otherAudio === false}
          />
          <Row label="Button held for this test" value={held ? "yes" : "no"} good={held} />
          <Row label="App is" value={appState} />
        </View>

        {/* The one combination that is known to lose the button, said before
            the walk rather than after it. Without a foreground service the
            process is reapable, and nothing re-claims the button when it comes
            back — see the notes in RawAudioModule. */}
        {settings.headsetTrigger && !settings.backgroundListening ? (
          <Text style={styles.warn}>
            Pocket listening is off, so nothing keeps this app running with the
            screen off. Android can reap it, and the button is not taken back
            when it returns. If presses stop landing after a few minutes in a
            pocket, this is the first thing to change.
          </Text>
        ) : null}

        <Pressable
          onPress={held ? release : hold}
          style={({ pressed }) => [
            styles.button,
            held && styles.buttonHeld,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.buttonText}>{held ? "Release the button" : "Hold the button"}</Text>
        </Pressable>
        <Text style={styles.hint}>
          While held, this app owns the earbud button and YouTube and music stop
          responding to it. Leaving this screen puts it back the way the setting
          has it.
        </Text>

        <Pressable
          onPress={cue}
          style={({ pressed }) => [styles.button, styles.buttonSecondary, pressed && styles.buttonPressed]}
        >
          <Text style={styles.buttonText}>Play the confirmation tone</Text>
        </Pressable>
        <Text style={styles.hint}>
          The sound a real press makes. If the tone is inaudible in the earbuds,
          a press that worked would still feel like one that did not.
        </Text>

        <View style={styles.summaryRow}>
          <Text style={styles.summary}>
            {taps.length} press{taps.length === 1 ? "" : "es"} seen
            {taps.length > 0 ? ` · ${backgroundTaps} with the app not in front` : ""}
          </Text>
          {taps.length > 0 ? (
            <Pressable onPress={() => setTaps([])} accessibilityRole="button">
              <Text style={styles.clear}>Clear</Text>
            </Pressable>
          ) : null}
        </View>

        <View style={styles.logBox}>
          {taps.length === 0 ? (
            <Text style={styles.logEmpty}>No presses yet.</Text>
          ) : (
            taps.map((tap, index) => (
              <Text key={index} style={styles.logLine}>
                {clockTime(tap.at)}  {tap.appState.padEnd(10)}
                {tap.keyCode === undefined ? "transport" : `key ${tap.keyCode}`}
              </Text>
            ))
          )}
        </View>

        {message ? <Text style={styles.message}>{message}</Text> : null}
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
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.xs },
  rowLabel: { color: colors.textMuted, fontSize: 14 },
  rowValue: { color: colors.text, fontSize: 14, fontWeight: "600" },
  good: { color: colors.good },
  bad: { color: colors.bad },
  warn: { color: colors.warn, fontSize: 13, lineHeight: 19 },
  button: {
    backgroundColor: colors.accent,
    paddingVertical: 16,
    borderRadius: radius.md,
    alignItems: "center",
  },
  buttonSecondary: { backgroundColor: colors.border },
  buttonHeld: { backgroundColor: colors.recording },
  buttonPressed: { opacity: 0.75 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 12, lineHeight: 17 },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  summary: { color: colors.textMuted, fontSize: 13 },
  clear: { color: colors.accent, fontSize: 13 },
  logBox: {
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    padding: spacing.md,
    minHeight: 120,
  },
  logEmpty: { color: colors.textFaint, fontSize: 12 },
  logLine: { color: "#b9c4d4", fontSize: 12, fontFamily: "monospace", marginBottom: 2 },
  message: { color: colors.textMuted, fontSize: 13 },
});
