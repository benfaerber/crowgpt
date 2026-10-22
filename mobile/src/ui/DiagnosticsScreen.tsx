import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  PermissionsAndroid,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import RawAudio, { type RecordingResult } from "../../modules/raw-audio";
// Only the page-end rule; this screen predates the theme and still
// hardcodes its colours.
import { pageEnd } from "./theme";

const METER_FLOOR_DB = -80;
const PROBE_MS = 1500;

/**
 * Field audio sits far below full scale — a crow a few meters off peaks around
 * -15 dBFS and its half-second RMS is ~0.01, which a linear bar renders as an
 * invisible 1%. Map dBFS onto the track instead so the meter has usable travel.
 *
 * The floor is -80 rather than -60 because capture runs on UNPROCESSED, which on
 * our phones sits ~17 dB below VOICE_RECOGNITION.
 */
function meterFraction(level: number): number {
  if (level <= 0) return 0;
  const db = 20 * Math.log10(level);
  return Math.min(1, Math.max(0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB));
}

async function requestMicPermission(): Promise<boolean> {
  if (Platform.OS !== "android") return true;
  const result = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
  );
  return result === PermissionsAndroid.RESULTS.GRANTED;
}

export function DiagnosticsScreen({ onBack }: { onBack: () => void }) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const [result, setResult] = useState<RecordingResult | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const subscription = useRef<{ remove(): void } | null>(null);

  const append = useCallback((line: string) => {
    setLog((previous) => [...previous, line]);
  }, []);

  useEffect(() => {
    try {
      setSupported(RawAudio.isUnprocessedSupported());
    } catch (error) {
      append(`isUnprocessedSupported threw: ${String(error)}`);
      setSupported(false);
    }
    return () => subscription.current?.remove();
  }, [append]);

  const start = useCallback(async () => {
    if (!(await requestMicPermission())) {
      append("RECORD_AUDIO denied");
      return;
    }
    try {
      subscription.current = RawAudio.addAudioLevelListener(({ level }) =>
        setLevel(level),
      );
      const path = await RawAudio.startRecording({ sampleRate: 48000 });
      setResult(null);
      setRecording(true);
      append(`recording -> ${path}`);
    } catch (error) {
      append(`start failed: ${String(error)}`);
    }
  }, [append]);

  const stop = useCallback(async () => {
    try {
      const info = await RawAudio.stopRecording();
      subscription.current?.remove();
      subscription.current = null;
      setRecording(false);
      setLevel(0);
      setResult(info);
      append(
        `stopped: ${info.durationMs} ms, ${info.bytes} bytes @ ${info.sampleRate} Hz`,
      );
      append(
        `path: source=${info.source}${info.sourceConfirmed ? "" : " (unconfirmed)"} ` +
          `effects=${info.effects.length === 0 ? "none" : info.effects.join(",")}`,
      );
      const expected = Math.round((info.bytes - 44) / 2 / info.sampleRate * 1000);
      append(`header check: ${expected} ms of PCM implied by byte count`);
    } catch (error) {
      append(`stop failed: ${String(error)}`);
    }
  }, [append]);

  const probe = useCallback(async () => {
    if (!(await requestMicPermission())) {
      append("RECORD_AUDIO denied");
      return;
    }
    append("probing mic sources… (~8s)");
    try {
      const report = await RawAudio.probeAudioSources({ millisPerSource: PROBE_MS });
      append(`property: ${report.propertyIsNull ? "null (unknown)" : report.propertyRaw}`);
      for (const source of report.sources) {
        if (!source.opened) {
          append(`  ${source.label}: FAILED TO OPEN (${source.state ?? source.error})`);
          continue;
        }
        const effects = source.configuration?.effects ?? [];
        const names = effects.length === 0 ? "none" : effects.map((e) => e.type).join(",");
        append(
          `  ${source.label}: got=${source.configuration?.clientAudioSourceLabel ?? "?"} ` +
            `effects=${names} rms=${source.rmsDbfs?.toFixed(1)}dBFS`,
        );
      }
    } catch (error) {
      append(`probe failed: ${String(error)}`);
    }
  }, [append]);

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <Pressable onPress={onBack} accessibilityRole="button">
          <Text style={styles.back}>‹ Settings</Text>
        </Pressable>
        <Text style={styles.title}>Mic diagnostics</Text>

        {/* Not certifying UNPROCESSED is normal and not a fault — what matters is
            the effects actually on the record path, reported per capture. */}
        <Row
          label="Certifies UNPROCESSED"
          value={
            supported === null
              ? "checking…"
              : supported
                ? "yes — using UNPROCESSED"
                : "no — using VOICE_RECOGNITION"
          }
          good={supported === true ? true : undefined}
        />

        <View style={styles.meterTrack}>
          <View
            style={[styles.meterFill, { width: `${Math.round(meterFraction(level) * 100)}%` }]}
          />
        </View>

        <Pressable
          onPress={recording ? stop : start}
          style={({ pressed }) => [
            styles.button,
            recording && styles.buttonRecording,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.buttonText}>{recording ? "Stop" : "Record"}</Text>
        </Pressable>

        {result && (
          <View style={styles.card}>
            <Row label="Duration" value={`${result.durationMs} ms`} />
            <Row label="Sample rate" value={`${result.sampleRate} Hz`} />
            <Row label="Size" value={`${result.bytes} bytes`} />
            <Row label="Source" value={result.source} />
            <Row
              label="Effects on path"
              value={result.effects.length === 0 ? "none" : result.effects.join(",")}
              good={result.effects.length === 0}
            />
          </View>
        )}

        <Pressable
          onPress={probe}
          disabled={recording}
          style={({ pressed }) => [
            styles.button,
            styles.buttonSecondary,
            recording && styles.buttonDisabled,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.buttonText}>Probe mic sources</Text>
        </Pressable>

        <View style={styles.logBox}>
          {log.length === 0 ? (
            <Text style={styles.logEmpty}>Log output appears here.</Text>
          ) : (
            log.map((line, index) => (
              <Text key={index} style={styles.logLine}>
                {line}
              </Text>
            ))
          )}
        </View>
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
  container: { flex: 1, backgroundColor: "#10141b" },
  content: { padding: 20, paddingTop: 64, gap: 12, paddingBottom: pageEnd },
  title: { color: "#e8eef7", fontSize: 22, fontWeight: "700", marginBottom: 8 },
  back: { color: "#2f6feb", fontSize: 16 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  rowLabel: { color: "#8b95a5", fontSize: 14 },
  rowValue: { color: "#e8eef7", fontSize: 14, fontWeight: "600" },
  good: { color: "#5ddc9a" },
  bad: { color: "#ff8a7a" },
  meterTrack: {
    height: 8,
    backgroundColor: "#1c2331",
    borderRadius: 4,
    overflow: "hidden",
  },
  meterFill: { height: 8, backgroundColor: "#5ddc9a" },
  button: {
    backgroundColor: "#2f6feb",
    paddingVertical: 16,
    borderRadius: 10,
    alignItems: "center",
  },
  buttonSecondary: { backgroundColor: "#37414f" },
  buttonRecording: { backgroundColor: "#c0392b" },
  buttonDisabled: { opacity: 0.4 },
  buttonPressed: { opacity: 0.75 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  card: { backgroundColor: "#1c2331", borderRadius: 10, padding: 12 },
  logBox: { backgroundColor: "#0b0e13", borderRadius: 8, padding: 12, minHeight: 120 },
  logEmpty: { color: "#5b6472", fontSize: 12 },
  logLine: { color: "#b9c4d4", fontSize: 12, fontFamily: "monospace", marginBottom: 2 },
});
