import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import type { AppServices } from "../app/AppServices";
import { newClientUuid } from "../domain/ids";
import { pickFamilyColor, type FamilyRecord } from "../domain/families";
import { deviceRandomBytes } from "../platform/random";
import { KeyboardAwareScroll } from "./components/KeyboardAwareScroll";
import { colors, radius, spacing , pageEnd} from "./theme";

/**
 * Create and review the crow families this device follows.
 *
 * Families are the unit of long-term identity: the same birds, on the same
 * territory, across months. They belong to this device — two recordists both
 * watching "the pair on the corner" mean different birds, and merging them
 * would corrupt the very thing a family is for.
 */
export function FamilyScreen({
  services,
  onBack,
  onCreated,
}: {
  services: AppServices;
  onBack: () => void;
  /** Fired with the new family so the caller can select it immediately. */
  onCreated?: (family: FamilyRecord) => void;
}) {
  const [families, setFamilies] = useState<FamilyRecord[]>([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  /** Which family's description is being edited, and its draft text. */
  const [editing, setEditing] = useState<{ uuid: string; draft: string }>();

  const refresh = useCallback(async () => {
    setFamilies(await services.families.list());
  }, [services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      const created = await services.families.add({
        uuid: newClientUuid(deviceRandomBytes),
        name: trimmed,
        // Chosen once and kept, so a family's glow on the map never changes
        // under you — the colour is how you recognise it at a glance.
        color: pickFamilyColor(families.map((f) => f.color)),
        notes: notes.trim() || undefined,
        createdAt: new Date().toISOString(),
      });
      setName("");
      setNotes("");
      await refresh();
      onCreated?.(created);
    } finally {
      setSaving(false);
    }
  };

  const saveNotes = async () => {
    if (!editing) return;
    // Clearing syncedAt re-queues the family for the next push; the server
    // adopts the phone's version, which is the only direction edits flow.
    await services.families.update(editing.uuid, {
      notes: editing.draft.trim() || undefined,
      syncedAt: undefined,
    });
    setEditing(undefined);
    await refresh();
  };

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>‹ Back</Text>
        </Pressable>
      </View>

      <KeyboardAwareScroll contentContainerStyle={styles.body}>
        <Text style={styles.title}>Families</Text>
        <Text style={styles.hint}>
          A family is a group of crows you follow over time. Optional — captures
          work fine without one.
        </Text>

        <View style={styles.card}>
          <Text style={styles.label}>New family</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="e.g. The Poe Family"
            placeholderTextColor={colors.textFaint}
            autoCapitalize="words"
            onSubmitEditing={create}
            returnKeyType="done"
          />
          <TextInput
            style={styles.input}
            value={notes}
            onChangeText={setNotes}
            placeholder="Description — e.g. 3 so far, looks like kids"
            placeholderTextColor={colors.textFaint}
          />
          <Pressable
            onPress={create}
            disabled={saving || name.trim().length === 0}
            style={({ pressed }) => [
              styles.action,
              styles.actionPrimary,
              (saving || name.trim().length === 0) && styles.disabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.actionText}>{saving ? "Creating…" : "Create family"}</Text>
          </Pressable>
        </View>

        {families.length === 0 ? (
          <Text style={styles.hint}>No families yet.</Text>
        ) : (
          families.map((family) => (
            <Pressable
              key={family.uuid}
              onPress={() =>
                setEditing((was) =>
                  was?.uuid === family.uuid
                    ? undefined
                    : { uuid: family.uuid, draft: family.notes ?? "" })
              }
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <View style={[styles.swatch, { backgroundColor: family.color, shadowColor: family.color }]} />
              <View style={styles.rowText}>
                <Text style={styles.rowName}>{family.name}</Text>
                {family.notes && editing?.uuid !== family.uuid ? (
                  <Text style={styles.rowNotes}>{family.notes}</Text>
                ) : null}
                <Text style={styles.rowMeta}>
                  {family.syncedAt
                    ? `synced · #${family.serverId}`
                    : family.serverId
                      ? "edited · syncs next push"
                      : "on phone only"}
                </Text>
                {editing?.uuid === family.uuid ? (
                  <View style={styles.editBox}>
                    <TextInput
                      style={styles.input}
                      value={editing.draft}
                      onChangeText={(draft) => setEditing({ uuid: family.uuid, draft })}
                      placeholder="Describe this family"
                      placeholderTextColor={colors.textFaint}
                      autoFocus
                      onSubmitEditing={saveNotes}
                      returnKeyType="done"
                    />
                    <Pressable
                      onPress={saveNotes}
                      style={({ pressed }) => [
                        styles.action, styles.actionPrimary, pressed && styles.pressed,
                      ]}
                    >
                      <Text style={styles.actionText}>Save description</Text>
                    </Pressable>
                  </View>
                ) : null}
              </View>
            </Pressable>
          ))
        )}

        <Text style={styles.footnote}>
          Individual crows within a family aren&apos;t tracked yet.
        </Text>
      </KeyboardAwareScroll>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: spacing.sm },
  back: { color: colors.accent, fontSize: 16 },
  pressed: { opacity: 0.6 },
  body: { paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: pageEnd },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 13 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm },
  label: { color: colors.text, fontSize: 14, fontWeight: "600" },
  input: {
    backgroundColor: colors.surfaceDeep,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
  action: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  actionPrimary: { backgroundColor: colors.accent },
  disabled: { opacity: 0.4 },
  actionText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  swatch: {
    width: 22,
    height: 22,
    borderRadius: 11,
    shadowOpacity: 0.9,
    shadowRadius: 8,
    elevation: 6,
  },
  rowText: { flex: 1, gap: 2 },
  rowName: { color: colors.text, fontSize: 15, fontWeight: "600" },
  rowNotes: { color: colors.textMuted, fontSize: 13 },
  rowMeta: { color: colors.textMuted, fontSize: 11 },
  editBox: { gap: spacing.sm, marginTop: spacing.xs },
  footnote: { color: colors.textFaint, fontSize: 12, marginTop: spacing.sm },
});
