import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colorForCall, type FleetConfig } from "../../domain/config";
import { colors, radius, spacing } from "../theme";

/** Shorter than this is almost always a mis-tap rather than a call. */
const MIN_SPAN_SEC = 0.3;

function clock(seconds: number): string {
  const whole = Math.max(0, seconds);
  return `${Math.floor(whole / 60)}:${String(Math.floor(whole % 60)).padStart(2, "0")}.${
    Math.floor((whole % 1) * 10)
  }`;
}

/**
 * Mark a call the detector never proposed.
 *
 * The reason this exists: BirdNET scores a begging fledgling at 0.06 — below any
 * usable threshold — so a third of the corpus analyzed to zero detections and
 * `begging` had zero examples despite being a core class with a trained head.
 * Confirming detections can only ever collect what the detector already finds,
 * which means the classes it is worst at can never gain training data. That is a
 * closed loop, and this is what opens it.
 *
 * By ear rather than by dragging: you find a call by listening, so the
 * interaction is play, tap at the start, tap at the end. Dragging a handle onto
 * a two-second call on a phone is precise work with a fingertip, and it would be
 * done while not listening.
 */
export function ManualLabel({
  config,
  playheadSec,
  duration,
  onCreate,
}: {
  config: FleetConfig;
  playheadSec: number;
  duration: number;
  onCreate: (span: { startSec: number; endSec: number; callType: string }) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [startSec, setStartSec] = useState<number>();
  const [endSec, setEndSec] = useState<number>();
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setStartSec(undefined);
    setEndSec(undefined);
    setOpen(false);
  };

  const span =
    startSec !== undefined && endSec !== undefined
      ? { start: Math.min(startSec, endSec), end: Math.max(startSec, endSec) }
      : undefined;
  const usable = span !== undefined && span.end - span.start >= MIN_SPAN_SEC;

  const create = async (callType: string) => {
    if (!span || saving) return;
    setSaving(true);
    try {
      await onCreate({ startSec: span.start, endSec: span.end, callType });
      reset();
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Pressable
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.add, pressed && styles.pressed]}
      >
        <Text style={styles.addText}>+ Mark a call the analyzer missed</Text>
      </Pressable>
    );
  }

  return (
    <View style={styles.panel}>
      <Text style={styles.hint}>
        Play the recording, then tap at the start of the call and again at its
        end.
      </Text>

      <View style={styles.marks}>
        <Pressable
          onPress={() => setStartSec(playheadSec)}
          style={({ pressed }) => [
            styles.mark,
            startSec !== undefined && styles.markSet,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.markLabel}>Start</Text>
          <Text style={styles.markValue}>
            {startSec === undefined ? "—" : clock(startSec)}
          </Text>
        </Pressable>

        <Pressable
          onPress={() => setEndSec(playheadSec)}
          style={({ pressed }) => [
            styles.mark,
            endSec !== undefined && styles.markSet,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.markLabel}>End</Text>
          <Text style={styles.markValue}>
            {endSec === undefined ? "—" : clock(endSec)}
          </Text>
        </Pressable>

        <View style={styles.mark}>
          <Text style={styles.markLabel}>Now</Text>
          <Text style={styles.markValue}>{clock(playheadSec)}</Text>
        </View>
      </View>

      {span && !usable ? (
        <Text style={styles.warn}>
          That span is {(span.end - span.start).toFixed(1)}s — too short to be a
          call. Tap the ends further apart.
        </Text>
      ) : null}

      {usable ? (
        <>
          <Text style={styles.hint}>
            {(span!.end - span!.start).toFixed(1)}s selected. What was it?
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={styles.choices}>
              {config.labels.map((def) => (
                <Pressable
                  key={def.key}
                  onPress={() => void create(def.key)}
                  disabled={saving}
                  style={({ pressed }) => [
                    styles.choice,
                    { borderColor: colorForCall(config, def.key) },
                    saving && styles.disabled,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.choiceText}>{def.text}</Text>
                </Pressable>
              ))}
            </View>
          </ScrollView>
        </>
      ) : null}

      <Pressable
        onPress={reset}
        style={({ pressed }) => [styles.cancel, pressed && styles.pressed]}
      >
        <Text style={styles.cancelText}>Cancel</Text>
      </Pressable>

      {duration > 0 && playheadSec >= duration - 0.05 ? (
        <Text style={styles.hint}>
          Playback is at the end — rewind to mark another call.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  add: {
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  addText: { color: colors.textMuted, fontSize: 13, fontWeight: "600" },
  panel: {
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    padding: spacing.md,
    gap: spacing.sm,
  },
  hint: { color: colors.textFaint, fontSize: 12 },
  warn: { color: colors.bad, fontSize: 12 },
  marks: { flexDirection: "row", gap: spacing.sm },
  mark: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
    borderWidth: 1.5,
    borderColor: "transparent",
  },
  markSet: { borderColor: colors.accent },
  markLabel: { color: colors.textFaint, fontSize: 11, textTransform: "uppercase" },
  markValue: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  choices: { flexDirection: "row", gap: spacing.sm, paddingVertical: 2 },
  choice: {
    borderWidth: 2,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  choiceText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  cancel: { alignItems: "center", paddingVertical: spacing.xs },
  cancelText: { color: colors.textMuted, fontSize: 12 },
  disabled: { opacity: 0.4 },
  pressed: { opacity: 0.7 },
});
