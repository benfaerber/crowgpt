import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../app/AppServices";
import { log } from "../app/Log";
import { LEVELS, type LogLevel, type StoredLogEntry } from "../domain/logging";
import { colors, radius, spacing , pageEnd} from "./theme";
import { useRememberedScroll } from "./useRememberedScroll";

const LEVEL_COLOR: Record<LogLevel, string> = {
  debug: colors.textFaint,
  info: colors.textMuted,
  warn: colors.warn,
  error: colors.bad,
};

/**
 * The app's log, on the phone that wrote it.
 *
 * The server copy is the one that gets read carefully, at a desk, with a
 * keyboard. This one exists for the other half of the problem: standing in a
 * park with no signal, having just watched something not work. Sending it
 * somewhere is no help then, and the answer is usually in the last four lines.
 *
 * Reads from storage when there is storage, and from memory when there is not —
 * "the database would not open" is a failure this screen has to be able to
 * show, and it is the one a SQLite-backed viewer would show as an empty list.
 */
export function LogScreen({
  services,
  onBack,
}: {
  services: AppServices;
  onBack: () => void;
}) {
  const scroll = useRememberedScroll("logs");
  const [entries, setEntries] = useState<StoredLogEntry[]>([]);
  const [floor, setFloor] = useState<LogLevel>("debug");
  const [pending, setPending] = useState(0);
  const [message, setMessage] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | undefined>();

  const refresh = useCallback(async () => {
    // Anything still queued is the most recent, which is the part being looked
    // for. Reading without flushing shows everything except what just happened.
    await log.flush();
    const store = services.logs;
    if (!store) {
      setMessage("No log store — showing what is still in memory.");
      setEntries(
        [...log.inMemory()]
          .reverse()
          .filter((entry) => LEVELS.indexOf(entry.level) >= LEVELS.indexOf(floor)),
      );
      return;
    }
    try {
      setEntries(await store.recent({ limit: 300, level: floor }));
      setPending(await store.countPending());
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : String(failure));
    }
  }, [floor, services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const send = async () => {
    setBusy(true);
    setMessage(undefined);
    const outcome = await services.syncLogs();
    setMessage(
      outcome.error
        ? `${outcome.sent} sent — then failed: ${outcome.error}`
        : outcome.sent === 0
          ? "Nothing new to send"
          : `${outcome.sent} sent to the server`,
    );
    setBusy(false);
    await refresh();
  };

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12}>
          <Text style={styles.back}>‹ Settings</Text>
        </Pressable>
        <Text style={styles.title}>App log</Text>
        <Text style={styles.hint}>
          What this phone has been saying about itself. Kept here, sent with the
          next sync, and readable on the dashboard afterwards.
        </Text>
      </View>

      <View style={styles.controls}>
        {LEVELS.map((level) => (
          <Pressable
            key={level}
            onPress={() => setFloor(level)}
            style={({ pressed }) => [
              styles.chip,
              floor === level && styles.chipOn,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.chipText, floor === level && styles.chipTextOn]}>
              {level}
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.controls}>
        <Pressable
          onPress={send}
          disabled={busy}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>
            {busy ? "Sending…" : `Send logs${pending > 0 ? ` (${pending})` : ""}`}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => void refresh()}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Refresh</Text>
        </Pressable>
        <Pressable
          onPress={async () => {
            await services.logs?.clear();
            await refresh();
          }}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        >
          <Text style={styles.actionText}>Clear</Text>
        </Pressable>
      </View>

      {message ? <Text style={styles.message}>{message}</Text> : null}

      <ScrollView {...scroll} contentContainerStyle={styles.body}>
        {entries.length === 0 ? (
          <Text style={styles.hint}>Nothing at this level.</Text>
        ) : (
          entries.map((entry) => (
            <Pressable
              key={entry.uuid}
              onPress={() =>
                setExpanded((current) => (current === entry.uuid ? undefined : entry.uuid))
              }
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <View style={styles.rowHead}>
                <Text style={[styles.level, { color: LEVEL_COLOR[entry.level] }]}>
                  {entry.level}
                </Text>
                <Text style={styles.tag}>{entry.tag}</Text>
                <Text style={styles.when}>{entry.at.slice(11, 19)}</Text>
                {entry.syncedAt ? null : <Text style={styles.unsent}>•</Text>}
              </View>
              <Text style={styles.message2}>{entry.message}</Text>
              {expanded === entry.uuid && entry.detail !== undefined ? (
                <Text style={styles.detail} selectable>
                  {typeof entry.detail === "string"
                    ? entry.detail
                    : JSON.stringify(entry.detail, null, 2)}
                </Text>
              ) : null}
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingTop: 56, gap: spacing.xs },
  back: { color: colors.accent, fontSize: 16 },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 12 },
  controls: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
  },
  chipOn: { backgroundColor: colors.accent },
  chipText: { color: colors.textMuted, fontSize: 12 },
  chipTextOn: { color: colors.background, fontWeight: "700" },
  action: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  actionText: { color: colors.accent, fontSize: 13, fontWeight: "600" },
  pressed: { opacity: 0.6 },
  message: {
    color: colors.textMuted,
    fontSize: 12,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  body: { padding: spacing.lg, gap: spacing.sm, paddingBottom: pageEnd },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    padding: spacing.sm,
    gap: 2,
  },
  rowHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  level: { fontSize: 11, fontWeight: "700" },
  tag: { color: colors.textMuted, fontSize: 11 },
  when: { color: colors.textFaint, fontSize: 11 },
  unsent: { color: colors.warn, fontSize: 14 },
  message2: { color: colors.text, fontSize: 13 },
  detail: {
    color: colors.textMuted,
    fontFamily: "monospace",
    fontSize: 11,
    paddingTop: spacing.xs,
  },
});
