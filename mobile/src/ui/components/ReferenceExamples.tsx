import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import { labelText, type FleetConfig } from "../../domain/config";
import { useReferencePlayer, type Reference } from "./ReferencePlayer";
import { colors, radius, spacing } from "../theme";

/**
 * "What did I call this last time?"
 *
 * Consistency across a season is the hard part of hand-labelling. A call marked
 * `alarm call` in July and the same sound marked `scold` in November is not two
 * data points, it is noise with a label on it — and nobody can hold a fortnight
 * of decisions in their head.
 *
 * So the previous decisions are one tap away while the next one is being made,
 * and they play from local audio, which means this works in a field with no
 * signal. That is the only place the question comes up.
 */
export function ReferenceExamples({
  services,
  config,
  callType,
  onClose,
}: {
  services: AppServices;
  config: FleetConfig;
  callType: string;
  onClose: () => void;
}) {
  const { examplesFor, play, stop, playing } = useReferencePlayer(services);
  const [examples, setExamples] = useState<Reference[] | undefined>();

  useEffect(() => {
    let live = true;
    void examplesFor(callType).then((found) => {
      if (live) setExamples(found);
    });
    return () => {
      live = false;
      stop();
    };
  }, [callType, examplesFor, stop]);

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <Text style={styles.title}>
          Your {labelText(config, callType).toLowerCase()} examples
        </Text>
        <Pressable onPress={onClose} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.close}>Done</Text>
        </Pressable>
      </View>

      {examples === undefined ? (
        <Text style={styles.hint}>Looking…</Text>
      ) : examples.length === 0 ? (
        <Text style={styles.hint}>
          Nothing marked {labelText(config, callType).toLowerCase()} yet — this one
          would be the first, so there is nothing to be consistent with.
        </Text>
      ) : (
        examples.map((example) => {
          const on = playing === example.label.uuid;
          return (
            <Pressable
              key={example.label.uuid}
              onPress={() => (on ? stop() : void play(example))}
              accessibilityRole="button"
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <Text style={styles.play}>{on ? "■" : "▶"}</Text>
              <Text style={styles.when}>
                {example.label.createdAt.slice(0, 10)} · {example.label.startSec.toFixed(1)}s
                {example.label.fromDetection ? "" : " · by ear"}
              </Text>
            </Pressable>
          );
        })
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.xs,
  },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: 13, fontWeight: "600" },
  close: { color: colors.accent, fontSize: 13, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 12 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  pressed: { opacity: 0.6 },
  play: { color: colors.accent, fontSize: 14, width: 18, textAlign: "center" },
  when: { color: colors.textMuted, fontSize: 12 },
});
