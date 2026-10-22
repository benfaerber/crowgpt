import { Pressable, StyleSheet, Text, View } from "react-native";

import Feather from "@expo/vector-icons/Feather";

import type { CaptureRecord } from "../../domain/types";
import { daysSinceRecorded, labelFreshness } from "../../domain/labelQueue";
import { describePlace, type LocationPrecision } from "../../domain/location";
import {
  colors,
  formatBytes,
  formatDuration,
  formatRecordedAt,
  radius,
  spacing,
  syncBadge,
  captureId,
} from "../theme";

export function CaptureRow({
  capture,
  uploadFraction,
  precision,
  onPress,
  onLongPress,
  selected,
  selecting,
  needsLabel,
  onDictate,
}: {
  capture: CaptureRecord;
  /** Kept, and nobody has said what is in it yet. */
  needsLabel?: boolean;
  /**
   * Speak a note about this one, in a tap.
   *
   * Only offered on the newest row. The capture screen is the note's home, but
   * reaching it is four taps and a scroll — and the whole premise is speaking
   * while the birds are still doing the thing, so the one moment that matters
   * must not cost a navigation.
   */
  onDictate?: () => void;
  /** 0..1 while this capture is the one being uploaded. */
  uploadFraction?: number;
  /** How precisely this recordist says where they were. */
  precision: LocationPrecision;
  onPress: () => void;
  onLongPress?: () => void;
  selected?: boolean;
  /** True while a selection is in progress, so every row shows its state. */
  selecting?: boolean;
}) {
  const state = capture.syncState;
  // Through the one function, always. "We masked it in three places and forgot
  // the fourth" is how a privacy setting fails, and this row is the one that
  // ends up in a screenshot of the app.
  const place = describePlace(capture, precision);
  // An uploaded capture that has since been edited is not "Synced" — saying so
  // while it sits in the pending count is how an edit looks like it was lost.
  const badge = syncBadge(capture);
  const id = captureId(capture);
  // Says how old rather than declaring the memory gone: the recordist is the
  // only one who knows whether they still remember, and a number lets them
  // decide. "5d" also explains itself, which "context lost" would not.
  const cold = needsLabel && labelFreshness(capture) === "cold";
  const age = cold ? daysSinceRecorded(capture) : 0;

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      accessibilityRole="button"
      accessibilityState={selecting ? { selected: Boolean(selected) } : undefined}
      style={({ pressed }) => [
        styles.row,
        pressed && styles.rowPressed,
        selected && styles.rowSelected,
      ]}
    >
      <View style={styles.header}>
        {/* Only while selecting. A permanent checkbox column would put a
            control on every row for a thing done rarely, and push the star —
            which answers the question people actually scan for — off the edge. */}
        {selecting ? (
          <Text style={[styles.tick, selected && styles.tickOn]}>
            {selected ? "\u25c9" : "\u25cb"}
          </Text>
        ) : null}
        {/* The name if there is one, the timestamp if not — never both as the
            headline, since a row that leads with a clock is one nobody scans.

            The star leads it, because in a list where most of the audio is
            seeded clips and test uploads, "is this a real field recording?" is
            the first thing worth knowing about a row. */}
        <Text style={styles.when} numberOfLines={1}>
          {capture.keep ? <Text style={styles.keep}>★ </Text> : null}
          {capture.name?.trim() || formatRecordedAt(capture.recordedAt)}
        </Text>
        {/* Beside the sync badge because it is the same kind of fact — a piece
            of outstanding work on this row — and because the star already
            taught the eye to look here. A label cannot be made later from
            nothing, so this is the one backlog on this screen that expires. */}
        {/* Nobody pressed the button on this one. As loud as the star, on the
            other side of the same question — the star says "a person vouches
            for this", AUTO says "no person was even there", and both are
            things the eye needs while sweeping junk out of an idle-mode night. */}
        {capture.trigger === "auto" ? (
          <View style={styles.auto}>
            <Text style={styles.autoText}>AUTO</Text>
          </View>
        ) : null}
        {needsLabel ? (
          cold ? (
            /* A different mark, not a louder one. Today's queue and last
               week's forgotten call are both unlabelled and are not the same
               job: one is remembering, the other is listening to a file and
               inferring, which is a weaker claim the corpus cannot tell apart
               afterwards. Muted rather than red — nothing is wrong, and a
               warning colour would ask for urgency that would not help. */
            <View style={styles.cold}>
              <Feather name="clock" size={10} color={colors.textMuted} />
              <Text style={styles.coldText}>{`${age}d`}</Text>
            </View>
          ) : (
            <View style={styles.toLabel}>
              <Text style={styles.toLabelText}>to label</Text>
            </View>
          )
        ) : null}
        <View style={[styles.badge, { borderColor: badge.color }]}>
          <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
        </View>
      </View>

      <View style={styles.footer}>
      <Text style={styles.meta} numberOfLines={1}>
        {/* Leads the line, because it is what a capture is called everywhere
            outside this phone — in the experiments, in phases/, and out loud.
            Absent until the first sync, and left out rather than faked: there
            is no id yet, and the badge on this row already says why. */}
        {id ? <Text style={styles.id}>{id} · </Text> : null}
        {/* When it was recorded stays available, just demoted below the name. */}
        {capture.name?.trim() ? `${formatRecordedAt(capture.recordedAt)} · ` : ""}
        {formatDuration(capture.durationMs)} · {formatBytes(capture.bytes)}
        {place ? ` · ${place}` : " · no location"}
      </Text>
      {/* In the row rather than over it. Absolutely positioned, this sat on top
          of the sync badge on a short row — a control overlapping the one word
          that says whether the recording is safe. */}
      {onDictate ? (
        <Pressable
          onPress={onDictate}
          accessibilityRole="button"
          accessibilityLabel="Record a spoken note about this capture"
          hitSlop={8}
          style={({ pressed }) => [styles.dictate, pressed && styles.rowPressed]}
        >
          <Feather name="mic" size={13} color={colors.accent} />
          <Text style={styles.dictateText}>Note</Text>
        </Pressable>
      ) : null}
      </View>

      {state === "syncing" && uploadFraction !== undefined && (
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${Math.round(uploadFraction * 100)}%` }]} />
        </View>
      )}

      {state === "failed" && capture.lastError && (
        <Text numberOfLines={2} style={styles.error}>
          {capture.lastError}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  rowSelected: {
    borderColor: colors.accent,
    backgroundColor: colors.selectedRow,
  },
  tick: {
    color: colors.textMuted,
    fontSize: 16,
    marginRight: spacing.sm,
  },
  tickOn: { color: colors.accent },
  rowPressed: { opacity: 0.75 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  when: { color: colors.text, fontSize: 15, fontWeight: "600", flexShrink: 1 },
  keep: { color: colors.warn },
  badge: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  badgeText: { fontSize: 11, fontWeight: "700" },
  auto: {
    borderWidth: 1,
    borderColor: colors.warn,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginRight: spacing.xs,
  },
  autoText: { color: colors.warn, fontSize: 11, fontWeight: "700" },
  toLabel: {
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginRight: spacing.xs,
  },
  toLabelText: { color: colors.accent, fontSize: 11, fontWeight: "700" },
  cold: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginRight: spacing.xs,
  },
  coldText: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  meta: { color: colors.textMuted, fontSize: 12, flexShrink: 1 },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  dictate: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  dictateText: { color: colors.accent, fontSize: 11, fontWeight: "700" },
  // Monospaced and a shade brighter: it is an identifier to be read off and
  // typed somewhere else, not prose.
  id: { color: colors.text, fontFamily: "monospace", fontVariant: ["tabular-nums"] },
  progressTrack: {
    height: 4,
    backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm,
    overflow: "hidden",
    marginTop: spacing.xs,
  },
  progressFill: { height: 4, backgroundColor: colors.accent },
  error: { color: colors.bad, fontSize: 11 },
});
