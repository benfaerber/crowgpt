import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Feather from "@expo/vector-icons/Feather";

import type { IdleControl } from "../../app/recorderView";
import type { IdleSessionState } from "../../recording/Recorder";
import { colors, radius, spacing } from "../theme";

/**
 * The armed hour's one control, and — since the first field test — its face.
 *
 * That test's verdict was "finicky", and the finickiness was really muteness:
 * the trigger heard everything and said nothing, so a threshold sitting just
 * over the playback level looked identical to a feature that was broken. The
 * cure is to show the machine's actual senses while armed: which phase it is
 * in, in words, and the meter it triggers from — what it hears in the crow
 * band right now, and the line it fires over. A level nudging the line says
 * "louder, or closer"; a level far under it says "this will never fire"; and
 * both are one glance instead of a mystery.
 *
 * A bar rather than a screen because arming happens on the way out the door.
 * The session itself runs natively and survives this screen unmounting; this
 * only renders it, polling once a second — the poll also drives the
 * countdown, so the two stay one clock.
 */
export function IdleBar({ idle }: { idle: IdleControl }) {
  const [now, setNow] = useState(Date.now());
  const [state, setState] = useState<IdleSessionState | null>(null);
  useEffect(() => {
    if (!idle.armed) {
      setState(null);
      return;
    }
    const tick = () => {
      setNow(Date.now());
      setState(idle.read());
    };
    tick();
    const timer = setInterval(tick, 1_000);
    return () => clearInterval(timer);
  }, [idle.armed, idle]);

  if (idle.armed) {
    const remainingMs = Math.max(0, (idle.deadline ?? now) - now);
    const minutes = Math.ceil(remainingMs / 60_000);
    const meter = state ? describeMeter(state) : null;
    return (
      <View style={[styles.bar, styles.armed]}>
        <View style={styles.armedRow}>
          <Feather name="zap" size={16} color={colors.warn} />
          <Text style={styles.armedText}>
            {phaseWords(state?.phase)} — {minutes} min left
            {idle.capturesMade > 0 ? ` · ${idle.capturesMade} auto` : ""}
          </Text>
          <Pressable
            onPress={() => void idle.disarm()}
            accessibilityRole="button"
            style={({ pressed }) => [styles.button, pressed && styles.pressed]}
          >
            <Text style={styles.buttonText}>Disarm</Text>
          </Pressable>
        </View>
        {meter ? (
          <Text style={styles.meter}>
            hearing{" "}
            <Text style={meter.nearly ? styles.meterHot : styles.meterBand}>
              {meter.band} dB
            </Text>
            {" "}in the crow band · fires over {meter.threshold} dB · floor{" "}
            {meter.floor}
          </Text>
        ) : null}
      </View>
    );
  }

  return (
    <View style={styles.bar}>
      <View style={styles.armedRow}>
        <Pressable
          onPress={() => void idle.arm()}
          accessibilityRole="button"
          style={({ pressed }) => [styles.button, pressed && styles.pressed]}
        >
          <Feather name="zap" size={14} color={colors.text} />
          <Text style={styles.buttonText}>Arm idle mode</Text>
        </Pressable>
        {idle.endedReason ? (
          <Text style={styles.ended}>{endedText(idle)}</Text>
        ) : null}
      </View>
    </View>
  );
}

/**
 * The phase in words a tired recordist parses at a glance. "Watching" rather
 * than "armed", because the bar's border already says armed — the word should
 * say what the machine is doing about it.
 */
function phaseWords(phase: IdleSessionState["phase"] | undefined): string {
  switch (phase) {
    case "triggered":
      return "Heard something — starting";
    case "recording":
      return "Recording a call";
    case "stopping":
      return "Call over — closing the capture";
    case "cooldown":
      return "Saved — refilling the buffer";
    case "suspended":
      return "Paused for your own recording";
    default:
      return "Watching for calls";
  }
}

function describeMeter(state: IdleSessionState) {
  const band = Math.round(state.bandDb);
  const threshold = Math.round(state.thresholdDb);
  return {
    band,
    threshold,
    floor: Math.round(state.floorDb),
    // Within 6 dB of firing: worth colouring, because "almost" is the state
    // that reads as broken from the outside.
    nearly: state.bandDb >= state.thresholdDb - 6,
  };
}

/**
 * Why the last session ended. The capture cap gets the loudest phrasing: it
 * means the threshold was wrong for the evening, which is the one outcome
 * that needs acting on.
 */
function endedText(idle: IdleControl): string {
  const captures = `${idle.capturesMade} auto capture${
    idle.capturesMade === 1 ? "" : "s"
  }`;
  switch (idle.endedReason) {
    case "expired":
      return `Last session ran its hour — ${captures}.`;
    case "captureCap":
      return `Last session hit the capture cap (${captures}) and gave up — the trigger was too eager.`;
    case "sessionFailed":
      return `Last session lost the microphone after ${captures}.`;
    default:
      return `Disarmed — ${captures}.`;
  }
}

const styles = StyleSheet.create({
  bar: {
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  armed: {
    backgroundColor: colors.surface,
    borderColor: colors.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  armedRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  armedText: { color: colors.text, flex: 1 },
  meter: { color: colors.textMuted, fontSize: 12, fontVariant: ["tabular-nums"] },
  meterBand: { color: colors.text, fontWeight: "600" },
  meterHot: { color: colors.warn, fontWeight: "700" },
  button: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
  },
  buttonText: { color: colors.text, fontWeight: "600" },
  pressed: { opacity: 0.6 },
  ended: { color: colors.textMuted, flex: 1, fontSize: 12 },
});
