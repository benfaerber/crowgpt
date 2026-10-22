import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppServices } from "../../app/AppServices";
import type { ContextRecord } from "../../domain/context";
import { newClientUuid } from "../../domain/ids";
import { deviceRandomBytes } from "../../platform/random";
import { colors, radius, spacing } from "../theme";

/**
 * Category tints and titles.
 *
 * Descriptive, never interpretive — an earlier version grouped "human walks
 * through" under "Threat", which answers the question the corpus exists to ask,
 * and gets it wrong for a recordist the birds know.
 *
 * Falls back to the server's raw category name for anything not listed, so a
 * category added by a config push still renders rather than vanishing.
 */
const CATEGORY_COLORS: Record<string, string> = {
  people: "#efb057",
  animals: "#f27070",
  food: "#6bd28a",
  crows: "#6ea8fe",
  quiet: "#9aa5b1",
};

const CATEGORY_TITLES: Record<string, string> = {
  people: "People",
  animals: "Animals",
  food: "Food",
  crows: "What the crows did",
  quiet: "Otherwise",
};

const CATEGORY_ORDER = ["people", "animals", "food", "crows", "quiet"];

/**
 * What was happening while *this call* was made.
 *
 * Per call, not per recording. A two-minute capture might have a dog appear at
 * 0:30 and leave at 0:50 — the alarm calls in that window are about the dog and
 * the song at 1:40 is not. Tagging the capture would credit every situation to
 * every call in it, and the co-occurrence table would report that crows sing at
 * dogs.
 *
 * The half with a deadline: a recording can be re-listened to and labelled a
 * year from now, but nobody can go back and check whether there was a dog. So
 * it is chips, grouped, one tap on and one tap off — no dialogs, no typing.
 */
export function ContextTagger({
  services,
  captureUuid,
  labelUuid,
  startSec,
  endSec,
  onChanged,
}: {
  services: AppServices;
  captureUuid: string;
  /**
   * The confirmed call this context belongs to.
   *
   * Omitted only on a capture confirmed to hold no calls, where the situation
   * is about the whole recording because there is no call to attach it to.
   */
  labelUuid?: string;
  startSec?: number;
  endSec?: number;
  onChanged?: () => void;
}) {
  const [events, setEvents] = useState<ContextRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const contexts = services.config.contexts;

  const refresh = useCallback(async () => {
    setEvents(
      labelUuid
        ? await services.context.forLabel(labelUuid)
        // Capture-level: everything on the recording, which on a silent one is
        // all of it. forLabel would match nothing, since these have no label.
        : (await services.context.forCapture(captureUuid)).filter((e) => !e.labelUuid),
    );
  }, [captureUuid, labelUuid, services]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggle = async (key: string) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const existing = events.find((event) => event.key === key);
      if (existing) {
        await services.removeContext(existing);
      } else {
        await services.addContext({
          uuid: newClientUuid(deviceRandomBytes),
          captureUuid,
          labelUuid,
          key,
          startSec,
          endSec,
        });
      }
      await refresh();
      onChanged?.();
    } catch (failure) {
      // A tag that fails silently is indistinguishable from a chip that does
      // not respond to touch, and the second is what it gets reported as. The
      // call was `void toggle(...)`, so anything thrown here vanished.
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  if (contexts.length === 0) {
    return (
      <Text style={styles.hint}>
        Sync once to fetch the list of situations from the server.
      </Text>
    );
  }

  // Server order for anything unrecognised, so a config push can introduce a
  // category without it being sorted to a surprising place.
  const categories = [...new Set(contexts.map((context) => context.category))].sort(
    (a, b) => {
      const rank = (c: string) =>
        CATEGORY_ORDER.indexOf(c) === -1 ? CATEGORY_ORDER.length : CATEGORY_ORDER.indexOf(c);
      return rank(a) - rank(b);
    },
  );

  return (
    <View style={styles.wrap}>
      <Text style={styles.hint}>
        What was happening during this call? Both what the world did and what the
        birds did — they are separate questions.
      </Text>

      {error ? <Text style={styles.error}>Couldn&apos;t save that tag — {error}</Text> : null}

      {categories.map((category) => (
        <View key={category} style={styles.group}>
          <Text style={[styles.category, { color: CATEGORY_COLORS[category] }]}>
            {CATEGORY_TITLES[category] ?? category}
          </Text>
          <View style={styles.chips}>
            {contexts
              .filter((context) => context.category === category)
              .map((context) => {
                const on = events.some((event) => event.key === context.key);
                const tint = CATEGORY_COLORS[category] ?? colors.accent;
                return (
                  <Pressable
                    key={context.key}
                    onPress={() => void toggle(context.key)}
                    style={({ pressed }) => [
                      styles.chip,
                      { borderColor: on ? tint : colors.border },
                      on && { backgroundColor: `${tint}22` },
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={[styles.chipText, on && styles.chipTextOn]}>
                      {on ? "✓ " : ""}
                      {context.text}
                    </Text>
                  </Pressable>
                );
              })}
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  error: { color: colors.bad, fontSize: 11 },
  wrap: { gap: spacing.sm, marginTop: spacing.xs },
  hint: { color: colors.textFaint, fontSize: 12 },
  group: { gap: spacing.xs },
  category: { fontSize: 11, fontWeight: "700", textTransform: "uppercase" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderWidth: 1.5,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surfaceDeep,
  },
  chipText: { color: colors.textMuted, fontSize: 13 },
  chipTextOn: { color: colors.text, fontWeight: "700" },
  pressed: { opacity: 0.6 },
});
