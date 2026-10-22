import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AudioInputDescription } from "../../recording/Recorder";
import { AUTO, reorder, type KnownMic } from "../../domain/micPriority";
import type { MicState } from "../../domain/micState";
import { log } from "../../app/Log";
import { colors, radius, spacing } from "../theme";

/**
 * Microphones in preference order.
 *
 * A single pinned input answered the wrong question. Android routes recording to
 * whatever it considers current — usually a paired headset — so *something* has
 * to be pinned, or a walk with earbuds in turns every capture into narrowband
 * speech audio with nothing on screen to say so. But pinning one input means the
 * morning you leave the good microphone at home, the app falls back to something
 * you never chose.
 *
 * A list answers it properly: first choice, second, then the phone's own, which
 * is always there. The recording uses the highest-ranked one actually attached,
 * and the capture stores which that turned out to be.
 *
 * Everything ever seen stays listed, greyed when absent. A list you can only
 * arrange while the hardware is plugged in is one you cannot arrange the evening
 * before — which is the only time anybody wants to.
 */
export function MicPicker({
  mics,
  attached,
  state,
  onChange,
}: {
  /** Remembered microphones, in priority order. */
  mics: KnownMic[];
  /** What is plugged in right now. */
  attached: AudioInputDescription[];
  /**
   * Which microphone is actually in use, worked out once in domain/micState and
   * passed in. This component used to decide for itself — the same question
   * answered a third way, which is how the picker could show the Rode as "in
   * use now" while the open session was on the phone mic.
   */
  state: MicState;
  onChange: (mics: KnownMic[]) => void;
}) {
  const here = new Set(attached.map((input) => input.preference));
  const isHere = (mic: KnownMic) =>
    mic.preference === "builtin" || mic.preference === "auto" || here.has(mic.preference);

  const active = state.preference;

  return (
    <View style={styles.group}>
      <Text style={styles.label}>Microphones, in order of preference</Text>
      <Text style={styles.hint}>
        The highest one that is plugged in gets used. The phone&apos;s own is always
        available, so it belongs last.
      </Text>

      {mics.map((mic, index) => {
        const present = isHere(mic);
        const inUse = mic.preference === active;
        return (
          <View
            key={mic.preference}
            style={[styles.row, inUse && styles.rowActive, !present && styles.rowAbsent]}
          >
            <Text style={styles.rank}>{index + 1}</Text>
            <View style={styles.text}>
              <Text style={[styles.name, !present && styles.nameAbsent]}>{mic.label}</Text>
              <Text style={styles.meta}>
                {inUse
                  ? state.live
                    ? "in use now"
                    : "next recording"
                  : present
                    ? "connected"
                    : mic.lastSeen
                      ? `not here · last seen ${mic.lastSeen.slice(0, 10)}`
                      : "not here"}
                {mic.typeLabel ? ` · ${mic.typeLabel}` : ""}
              </Text>
            </View>
            <Pressable
              onPress={() => onChange(reorder(mics, index, index - 1))}
              disabled={index === 0}
              accessibilityRole="button"
              accessibilityLabel={`Move ${mic.label} up`}
              style={({ pressed }) => [
                styles.arrow, index === 0 && styles.arrowOff, pressed && styles.pressed,
              ]}
            >
              <Text style={styles.arrowText}>▲</Text>
            </Pressable>
            <Pressable
              onPress={() => onChange(reorder(mics, index, index + 1))}
              disabled={index === mics.length - 1}
              accessibilityRole="button"
              accessibilityLabel={`Move ${mic.label} down`}
              style={({ pressed }) => [
                styles.arrow,
                index === mics.length - 1 && styles.arrowOff,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.arrowText}>▼</Text>
            </Pressable>
          </View>
        );
      })}

      {/* The same sentence the capture screen shows, from the same place. It
          belongs here too: this is the screen somebody opens to find out why
          the microphone they plugged in is not the one being used. */}
      {state.warning ? <Text style={styles.warning}>{state.warning}</Text> : null}

      {/* Offered rather than assumed. "auto" is what routes a capture through
          earbuds, so it should only ever happen because somebody added it. */}
      {mics.some((m) => m.preference === "auto") ? null : (
        <Pressable
          onPress={() =>
            onChange([...mics, { ...AUTO }])
          }
          style={({ pressed }) => [styles.add, pressed && styles.pressed]}
        >
          <Text style={styles.addText}>+ Add &ldquo;whatever Android picks&rdquo;</Text>
        </Pressable>
      )}
    </View>
  );
}

/**
 * Read the attached microphones once per mount — a mic can be plugged in while
 * the app is open, and reopening Settings is the natural way to notice.
 *
 * The callback is held in a ref rather than being an effect dependency: callers
 * pass an inline arrow, so depending on its identity would re-run the effect on
 * every render, and the effect sets state — which renders again.
 */
/**
 * The attached microphones, asked for once when this screen opens.
 *
 * `refresh` goes to the audio HAL and is therefore asynchronous — enumerating
 * inline used to block the interface. `list` reads the snapshot it leaves
 * behind.
 */
export function useAudioInputs(
  list: () => AudioInputDescription[],
  refresh?: () => Promise<unknown>,
): AudioInputDescription[] {
  const [inputs, setInputs] = useState<AudioInputDescription[]>([]);
  const listRef = useRef(list);
  listRef.current = list;
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    let live = true;
    const read = () => {
      try {
        if (live) setInputs(listRef.current());
      } catch {
        // Never on a device with the native module; keep Settings usable anyway.
        if (live) setInputs([]);
      }
    };
    void (refreshRef.current?.() ?? Promise.resolve()).then(read).catch((failure) => {
      // Rendered from the stale list either way, but no longer silently:
      // success and failure used to run the same handler, so a refresh
      // that always threw looked like a picker that was simply out of date.
      log.warn("recorder", "could not refresh microphones for the picker", failure);
      read();
    });
    return () => {
      live = false;
    };
  }, []);

  return inputs;
}

const styles = StyleSheet.create({
  group: { gap: spacing.xs },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 11, marginBottom: spacing.xs },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  rowActive: { borderColor: colors.good },
  rowAbsent: { opacity: 0.55 },
  rank: {
    color: colors.textFaint,
    fontSize: 12,
    fontWeight: "700",
    width: 16,
    textAlign: "center",
  },
  text: { flex: 1, gap: 1 },
  name: { color: colors.text, fontSize: 14 },
  nameAbsent: { color: colors.textMuted },
  meta: { color: colors.textFaint, fontSize: 11 },
  arrow: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceDeep,
  },
  arrowOff: { opacity: 0.25 },
  arrowText: { color: colors.text, fontSize: 12 },
  warning: { color: colors.warn, fontSize: 11, marginTop: spacing.xs },
  pressed: { opacity: 0.7 },
  add: { paddingVertical: spacing.sm },
  addText: { color: colors.accent, fontSize: 12, fontWeight: "600" },
});
