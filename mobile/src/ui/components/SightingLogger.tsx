import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import { newClientUuid } from "../../domain/ids";
import { deviceRandomBytes } from "../../platform/random";
import { describeOffset, type SightingRecord } from "../../domain/sightings";
import { colors, radius, spacing } from "../theme";

/** Offsets people actually report, so the common case is one tap. */
const WHEN = [
  { label: "5 min before", sec: -300 },
  { label: "1 min before", sec: -60 },
  { label: "just after", sec: 30 },
  { label: "1 min after", sec: 60 },
  { label: "5 min after", sec: 300 },
  { label: "15 min after", sec: 900 },
];

/**
 * Log something seen near this recording but *not* during it.
 *
 * Kept visibly apart from the context tagger, and worded to make the boundary
 * hard to cross by accident: "Seen nearby, not during". If this reads as another
 * way to tag context, it will be used as one, and then the calls × context
 * matrix quietly starts confirming whatever was inferred from the sighting.
 *
 * Choosing a time is required — it is the only thing distinguishing a sighting
 * from a context event, so the Save button stays disabled until one is picked
 * rather than defaulting to zero.
 */
export function SightingLogger({
  services,
  captureUuid,
}: {
  services: AppServices;
  captureUuid: string;
}) {
  const [rows, setRows] = useState<SightingRecord[]>([]);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState<string>();
  const [offsetSec, setOffsetSec] = useState<number>();
  const [notes, setNotes] = useState("");

  const refresh = () =>
    void services.sightings.forCapture(captureUuid).then(setRows);
  useEffect(refresh, [captureUuid, services]);

  const contexts = services.config.contexts;
  const label = (k: string) => contexts.find((c) => c.key === k)?.text ?? k;

  const save = async () => {
    if (!key || offsetSec === undefined) return;
    await services.sightings.add({
      uuid: newClientUuid(deviceRandomBytes),
      captureUuid,
      key,
      offsetSec,
      notes: notes.trim() || undefined,
      createdAt: new Date().toISOString(),
    });
    setKey(undefined);
    setOffsetSec(undefined);
    setNotes("");
    setOpen(false);
    refresh();
  };

  return (
    <View style={styles.card}>
      <Pressable
        onPress={() => setOpen((was) => !was)}
        accessibilityRole="button"
        style={({ pressed }) => [styles.summary, pressed && styles.pressed]}
      >
        <View style={styles.heading}>
          <Text style={styles.label}>Seen nearby, not during</Text>
          <Text style={styles.hint}>
            Kept separate from tagged context — it is a lead, not ground truth.
          </Text>
        </View>
        <Text style={styles.chevron}>{open ? "▲" : "▼"}</Text>
      </Pressable>

      {rows.map((row) => (
        <View key={row.uuid} style={styles.row}>
          <Text style={styles.rowText}>
            {label(row.key)} · {describeOffset(row.offsetSec)}
            {row.notes ? ` · ${row.notes}` : ""}
          </Text>
          <Pressable
            onPress={async () => {
              await services.sightings.remove(row.uuid);
              refresh();
            }}
            accessibilityLabel="Remove sighting"
            style={({ pressed }) => [pressed && styles.pressed]}
          >
            <Text style={styles.remove}>×</Text>
          </Pressable>
        </View>
      ))}

      {open && (
        <View style={styles.form}>
          <Text style={styles.section}>What</Text>
          <View style={styles.chips}>
            {contexts.map((context) => (
              <Pressable
                key={context.key}
                onPress={() => setKey(context.key)}
                style={({ pressed }) => [
                  styles.chip,
                  context.key === key && styles.chipOn,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={context.key === key ? styles.chipTextOn : styles.chipText}>
                  {context.text}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.section}>When, relative to the recording</Text>
          <View style={styles.chips}>
            {WHEN.map((when) => (
              <Pressable
                key={when.sec}
                onPress={() => setOffsetSec(when.sec)}
                style={({ pressed }) => [
                  styles.chip,
                  when.sec === offsetSec && styles.chipOn,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={when.sec === offsetSec ? styles.chipTextOn : styles.chipText}>
                  {when.label}
                </Text>
              </Pressable>
            ))}
          </View>

          <TextInput
            style={styles.input}
            value={notes}
            onChangeText={setNotes}
            placeholder="e.g. 2 hawks, from the apartment window, a block away"
            placeholderTextColor={colors.textFaint}
            multiline
          />

          <Pressable
            onPress={save}
            disabled={!key || offsetSec === undefined}
            accessibilityRole="button"
            style={({ pressed }) => [
              styles.save,
              (!key || offsetSec === undefined) && styles.saveDisabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.saveText}>
              {offsetSec === undefined ? "Pick a time" : "Save sighting"}
            </Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  summary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.md,
    gap: spacing.sm,
  },
  heading: { flex: 1, gap: 2 },
  pressed: { opacity: 0.7 },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  hint: { color: colors.textFaint, fontSize: 11 },
  chevron: { color: colors.textFaint, fontSize: 10 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  rowText: { color: colors.text, fontSize: 13, flex: 1 },
  remove: { color: colors.textFaint, fontSize: 18, paddingHorizontal: spacing.sm },
  form: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  section: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.surfaceDeep },
  chipText: { color: colors.textMuted, fontSize: 12 },
  chipTextOn: { color: colors.accent, fontSize: 12, fontWeight: "600" },
  input: {
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    color: colors.text,
    padding: spacing.sm,
    minHeight: 54,
    fontSize: 13,
  },
  save: {
    backgroundColor: colors.accent,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  saveDisabled: { opacity: 0.4 },
  saveText: { color: "#fff", fontSize: 13, fontWeight: "700" },
});
