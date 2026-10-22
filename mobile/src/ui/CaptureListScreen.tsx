import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { AppServices, Settings } from "../app/AppServices";
import { useCaptures } from "../app/useCaptures";
import { useRecorderView } from "../app/RecorderContext";
import type { CaptureRecord } from "../domain/types";
import { applyView, DEFAULT_VIEW, describeView, type CaptureView }
  from "../domain/captureFilters";
import { CaptureFilterBar } from "./components/CaptureFilterBar";
import { CaptureRow } from "./components/CaptureRow";
import { labelQueue, needsLabelling } from "../domain/labelQueue";
import { PendingCaptureRow } from "./components/PendingCaptureRow";
import { mergeCaptures, MergeFailed } from "../domain/mergeCaptures";
import { writeMergedAudio } from "../platform/writeMergedAudio";
import { newClientUuid } from "../domain/ids";
import { deviceRandomBytes } from "../platform/random";
import { RecordButton } from "./components/RecordButton";
import { IdleBar } from "./components/IdleBar";
import { CaptureLock } from "./components/CaptureLock";
import { Flock } from "./components/Flock";
import { screenLocked } from "../domain/captureLock";
import { SyncBar } from "./components/SyncBar";
import { colors, pageEnd, radius, spacing } from "./theme";
import { useBrandTitleFont } from "./brandFont";
import { useRememberedScroll } from "./useRememberedScroll";
import Feather from "@expo/vector-icons/Feather";

export function CaptureListScreen({
  services,
  onSettingsChange,
  recordedTick,
  view: filters,
  onViewChange: setFilters,
  onOpenCapture,
  onOpenSettings,
  onOpenGuide,
  onOpenMap,
  onRecordVideo,
}: {
  services: AppServices;
  /** Applies a settings change — the pocket-mic switch is the only one here. */
  onSettingsChange: (settings: Settings) => void;
  /**
   * Rises when a capture has been written. The recorder outlives this screen
   * now, so a headset press from Settings finishes a capture with nothing here
   * mounted to hear about it — this is how the list learns it missed one.
   */
  recordedTick: number;
  /** Shared with the map — the same selection, rendered differently. */
  view: CaptureView;
  onViewChange: (view: CaptureView) => void;
  onOpenCapture: (capture: CaptureRecord) => void;
  onOpenSettings: () => void;
  /** The field guide — what to record, and how to read the birds. */
  onOpenGuide: () => void;
  onOpenMap: () => void;
  onRecordVideo: () => void;
}) {
  const scroll = useRememberedScroll("list");
  const brandFont = useBrandTitleFont();
  const view = useCaptures(services);
  const recorder = useRecorderView();
  // Only when the number actually moves. `useCaptures` already loads on mount,
  // so refreshing on the first render as well would fetch the same rows twice
  // on every trip back from Settings.
  const seenTick = useRef(recordedTick);
  useEffect(() => {
    if (recordedTick === seenTick.current) return;
    seenTick.current = recordedTick;
    view.refresh();
  }, [recordedTick, view]);
  /**
   * Show only captures marked as real observations.
   *
   * The corpus is mostly seeded clips and test uploads, so scrolling for a
   * particular morning's fieldwork means scrolling past everything that isn't.
   * Off by default so nothing silently disappears.
   */
  const kept = useMemo(
    () => view.captures.filter((capture) => capture.keep).length,
    [view.captures],
  );
  const shown = useMemo(() => {
    const inView = applyView(view.captures, filters);
    // The queue re-sorts to newest-first regardless of the order pill, because
    // that ordering IS the feature: a label is worth most while the recordist
    // still remembers watching it happen.
    return filters.unlabelledOnly ? labelQueue(inView, view.labelCounts) : inView;
  }, [view.captures, view.labelCounts, filters]);

  const waiting = useMemo(
    () => view.captures.filter((c) => needsLabelling(c, view.labelCounts.get(c.uuid) ?? 0)),
    [view.captures, view.labelCounts],
  );
  const narrowed = describeView(filters, shown.length, view.captures.length);

  /**
   * Captures picked out for merging, by uuid.
   *
   * Long-press opens the selection; tapping adds and removes while it is open;
   * clearing it closes. A separate mode rather than an always-on checkbox
   * column, because merging is rare and the list's job the rest of the time is
   * to be scanned.
   */
  const [selected, setSelected] = useState<string[]>([]);

  /**
   * Cleared when the capture ends, so the next one arms itself.
   *
   * Per capture rather than per session on purpose: unlocking to stop one
   * recording should not leave the screen open for the next, which is the
   * version of this feature that quietly stops working after the first use.
   */
  const [unlocked, setUnlocked] = useState(false);
  useEffect(() => {
    if (!recorder.recording) setUnlocked(false);
  }, [recorder.recording]);
  const locked = screenLocked({
    enabled: services.settings.captureLock,
    recording: recorder.recording,
    unlocked,
  });
  const selecting = selected.length > 0;
  const [merging, setMerging] = useState(false);
  const [deleting, setDeleting] = useState(false);
  /** Counts up per tap on the brand mark; zero when no flock is in the air. */
  const [flight, setFlight] = useState(0);

  const toggle = (uuid: string) =>
    setSelected((current) => current.includes(uuid)
      ? current.filter((u) => u !== uuid)
      : [...current, uuid]);

  /**
   * How many of the selected captures are marked ★ Keep.
   *
   * Named in the confirmation because the flag is the only thing telling a real
   * field recording from a seeded archive clip, and clearing out test uploads
   * in bulk is exactly when one gets swept along with them.
   */
  const keptSelected = view.captures.filter(
    (c) => selected.includes(c.uuid) && c.keep,
  ).length;

  const doDelete = () => {
    const count = selected.length;
    Alert.alert(
      count === 1 ? "Delete this capture?" : `Delete ${count} captures?`,
      [
        "The audio is removed from this phone and cannot be recovered here.",
        keptSelected > 0
          ? `${keptSelected} of them ${keptSelected === 1 ? "is" : "are"} marked ★ Keep.`
          : undefined,
        "Anything already synced stays on the server.",
      ]
        .filter(Boolean)
        .join("\n\n"),
      [
        { text: "Cancel", style: "cancel" },
        {
          text: count === 1 ? "Delete" : `Delete ${count}`,
          style: "destructive",
          onPress: () => {
            setDeleting(true);
            void services
              .deleteCaptures(selected)
              .then(() => {
                setSelected([]);
                return view.refresh();
              })
              .catch((failure) =>
                Alert.alert(
                  "Could not delete",
                  failure instanceof Error ? failure.message : "Something went wrong.",
                ),
              )
              .finally(() => setDeleting(false));
          },
        },
      ],
    );
  };

  const doMerge = async () => {
    // Ordering is by recordedAt inside mergeCaptures, so the order they were
    // tapped in does not matter and is not shown as if it did.
    const uuid = newClientUuid(deviceRandomBytes);
    // Read before merging: afterwards they are out of `captures`.
    const selectedParts = view.captures.filter((c) => selected.includes(c.uuid));
    setMerging(true);
    try {
      const { merged } = await mergeCaptures(services.repository, selected, {
        captureUuid: uuid,
        mediaUuid: newClientUuid(deviceRandomBytes),
      });
      // Written to disk rather than assembled on read. Playback, the waveform
      // and the normaliser all hand a file:// URI to the OS, so a capture with
      // no file behind it shows a player that never loads and a size of zero.
      const parts = (merged.mergedFrom ?? []).map((partUuid) => {
        const part = selectedParts.find((p) => p.uuid === partUuid)!;
        return { uuid: part.uuid, audioPath: part.audioPath };
      });
      const audio = await writeMergedAudio(uuid, parts);
      const withAudio = await services.repository.update(merged.uuid, {
        audioPath: audio.path,
        bytes: audio.bytes,
      });
      setSelected([]);
      await view.refresh();
      onOpenCapture(withAudio);
    } catch (failure) {
      Alert.alert(
        "Could not merge",
        failure instanceof MergeFailed || failure instanceof Error
          ? failure.message
          : "Something went wrong.",
      );
    } finally {
      setMerging(false);
    }
  };

  return (
    <View style={styles.screen}>
      {/* Last child, so it paints over everything and takes every touch. A lock
          that left one control reachable would be protecting the wrong thing —
          the stray touch lands wherever it lands. */}
      <View style={styles.header}>
        <View style={styles.brand}>
          {/* Tapping the mark sends the Poe family across the screen — the
              promo site's flock, answering here. Retapping mid-flight remounts
              a fresh flock via the changing key. */}
          <Pressable
            onPress={() => setFlight((n) => n + 1)}
            accessibilityRole="image"
            accessibilityLabel="CrowGPT"
            hitSlop={10}
            style={({ pressed }) => [pressed && styles.pressed]}
          >
            <Image source={require("../../assets/brand-mark.png")} style={styles.brandMark} />
          </Pressable>
          <Text style={[styles.title, brandFont]}>CrowGPT</Text>
        </View>
        <View style={styles.headerActions}>
        <Pressable
          onPress={onOpenGuide}
          accessibilityRole="button"
          accessibilityLabel="Field guide"
          style={({ pressed }) => [styles.settings, pressed && styles.pressed]}
        >
          <Feather name="book-open" size={22} color={colors.textMuted} />
        </Pressable>
        <Pressable
          onPress={onOpenMap}
          accessibilityRole="button"
          accessibilityLabel="Map"
          style={({ pressed }) => [styles.settings, pressed && styles.pressed]}
        >
          <Feather name="map" size={22} color={colors.textMuted} />
        </Pressable>
        <Pressable
          onPress={onOpenSettings}
          accessibilityRole="button"
          accessibilityLabel="Settings"
          style={({ pressed }) => [styles.gear, pressed && styles.pressed]}
        >
          {/* A drawn icon rather than U+2699, which Android renders as
              something closer to a dharma wheel than a gear. */}
          <Feather name="settings" size={22} color={colors.textMuted} />
        </Pressable>
        </View>
      </View>

      <View style={styles.controls}>
        <RecordButton
          recording={recorder.recording}
          listening={recorder.listening}
          bufferedMs={recorder.bufferedMs}
          level={recorder.level}
          elapsedMs={recorder.elapsedMs}
          // NOT disabled while syncing, which is what it used to do and is why
          // the button "randomly stopped working". A sync uploads captures that
          // already exist; a new recording writes a new file and a new row and
          // cannot collide with one. So the cost of the gate was entirely on the
          // wrong side: an upload against an unreachable server holds it for as
          // long as the timeouts take, and a disabled Pressable never fires
          // onPress — no error, no log line, nothing to find afterwards. It
          // dates from the first version of this screen, before the recorder
          // had any of the care it has now, and was never a decision.
          //
          // The rule it breaks is the one this app is built on: a recording that
          // did not happen is the only loss that cannot be undone, so nothing
          // that touches the network may stand between a crow and the button.
          micLabel={recorder.micLabel}
          headsetArmed={recorder.headsetArmed}
          // Only with the rolling buffer on: without it there is no session to
          // hold from a pocket, and a control that silently does nothing is
          // worse than no control.
          pocket={
            services.settings.preRoll
              ? {
                  on: services.settings.backgroundListening,
                  onChange: (backgroundListening) => {
                    onSettingsChange({ ...services.settings, backgroundListening });
                    if (backgroundListening) {
                      void services.permissions.request("notifications");
                    }
                  },
                }
              : undefined
          }
          onPress={recorder.toggle}
          onRecordVideo={onRecordVideo}
          videoDisabled={recorder.recording || view.syncing}
        />
        {recorder.error ? <Text style={styles.error}>{recorder.error}</Text> : null}
        {recorder.micNote ? <Text style={styles.micNote}>{recorder.micNote}</Text> : null}
        {recorder.notice ? <Text style={styles.notice}>{recorder.notice}</Text> : null}

        {/* Only with the setting on: the bar is a loaded control — it opens
            the microphone and starts recordings unattended — and it must not
            sit on the main screen of every phone that never asked for it. */}
        {/* Both switches, not just its own: idle mode lives nested under the
            rolling buffer in Settings, and a stored idleMode surviving a
            preRoll turned off elsewhere must not resurface the Arm button. */}
        {services.settings.preRoll && services.settings.idleMode
          ? <IdleBar idle={recorder.idle} />
          : null}

        <SyncBar
          warning={view.compatibilityWarning}
          pendingCount={view.pendingCount}
          syncing={view.syncing}
          lastMessage={view.lastMessage}
          progress={view.progress}
          onSync={view.sync}
          onCancel={view.cancelSync}
        />

        <CaptureFilterBar
          view={filters}
          keptCount={kept}
          waitingCount={waiting.length}
          onChange={setFilters}
        />
      </View>

      <ScrollView {...scroll} contentContainerStyle={styles.list}>
        {/* Loud when filtering, because a quiet one reads as data loss. It did:
            four captures showing out of forty was reported as "all my captures
            disappeared", and only a reinstall — which resets this state — made
            them come back. */}
        {narrowed ? (
          <Pressable
            onPress={() => setFilters(DEFAULT_VIEW)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.filterBanner, pressed && styles.pressed]}
          >
            <Text style={styles.filterBannerText}>{narrowed} — tap to clear</Text>
          </Pressable>
        ) : null}

        {/* Above the real rows, because a recording that has just been made is
            the newest thing there is and the list is newest-first. It is also
            where the recordist is already looking. */}
        {recorder.pending.map((entry) => (
          <PendingCaptureRow key={entry.id} pending={entry} />
        ))}

        {shown.length === 0 && recorder.pending.length === 0 ? (
          <View style={styles.empty}>
            {/* Three different empty states, because they need three different
                reactions. "Couldn't read" is the alarming one and used to be
                indistinguishable from "you have none" — which is how a working
                store got reported twice as every capture disappearing. */}
            {view.readError ? (
              <>
                <Text style={styles.emptyTitleBad}>Couldn&apos;t read the store</Text>
                <Text style={styles.emptyBody}>
                  Your recordings are still on the phone — this is a read that
                  failed, not an empty library. {view.readError}
                </Text>
              </>
            ) : narrowed ? (
              <>
                <Text style={styles.emptyTitle}>Nothing matches</Text>
                <Text style={styles.emptyBody}>
                  {view.captures.length} capture{view.captures.length === 1 ? "" : "s"} on
                  this phone. Tap the banner above to clear the filters.
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.emptyTitle}>No captures yet</Text>
                <Text style={styles.emptyBody}>
                  Recordings are kept on this phone and stay here until you tap Sync.
                </Text>
              </>
            )}
          </View>
        ) : (
          shown.map((capture) => (
            <CaptureRow
              key={capture.uuid}
              capture={capture}
              needsLabel={needsLabelling(capture, view.labelCounts.get(capture.uuid) ?? 0)}
              precision={services.settings.locationPrecision}
              uploadFraction={
                view.syncingUuid === capture.uuid ? view.progress?.fraction : undefined
              }
              selecting={selecting}
              selected={selected.includes(capture.uuid)}
              onLongPress={() => toggle(capture.uuid)}
              onPress={() =>
                selecting ? toggle(capture.uuid) : onOpenCapture(capture)}
              // Only the newest, and only when nothing else is using the
              // microphone. A "Note" button on every row would be a column of
              // controls for a thing done once per capture; on the top row it
              // is the difference between speaking now and typing it up
              // tonight, which is the whole feature.
              onDictate={
                capture.uuid === shown[0]?.uuid && !recorder.recording
                && recorder.dictation.phase === "idle"
                  ? () => {
                      void recorder.dictation.start(capture.uuid);
                      onOpenCapture(capture);
                    }
                  : undefined
              }
            />
          ))
        )}
      </ScrollView>

      {/* Only while selecting, and anchored to the bottom where a thumb is.
          Says how many and what will happen, because "Merge" alone does not
          tell you that four recordings are about to become one. */}
      {selecting ? (
        <View style={styles.selectionBar}>
          <View style={styles.selectionText}>
            <Text style={styles.selectionCount}>
              {selected.length} selected
            </Text>
            <Text style={styles.selectionHint}>
              {deleting
                ? "Deleting…"
                : keptSelected > 0
                  ? `${keptSelected} of them ★ kept — deleting cannot be undone`
                  : selected.length < 2
                    ? "Pick another to merge, or delete this one"
                    : "Joined oldest first, 3s of silence between"}
            </Text>
          </View>
          <Pressable
            onPress={() => setSelected([])}
            accessibilityRole="button"
            style={({ pressed }) => [styles.selectionCancel, pressed && styles.pressed]}
          >
            <Text style={styles.selectionCancelText}>Cancel</Text>
          </Pressable>
          {/* Beside Merge because it acts on the same selection, and confirmed
              first: the corpus has a handful of real field recordings among the
              seeded clips, and a mis-tap here is the one loss nothing undoes. */}
          <Pressable
            onPress={doDelete}
            disabled={deleting || merging}
            accessibilityRole="button"
            accessibilityLabel={`Delete ${selected.length} captures`}
            style={({ pressed }) => [
              styles.deleteButton,
              (deleting || merging) && styles.mergeButtonOff,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.mergeButtonText}>Delete</Text>
          </Pressable>
          <Pressable
            onPress={doMerge}
            disabled={selected.length < 2 || merging}
            accessibilityRole="button"
            style={({ pressed }) => [
              styles.mergeButton,
              (selected.length < 2 || merging) && styles.mergeButtonOff,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.mergeButtonText}>
              {merging ? "Merging…" : "Merge"}
            </Text>
          </Pressable>
        </View>
      ) : null}

      {flight > 0 && <Flock key={flight} onDone={() => setFlight(0)} />}

      {locked ? (
        <CaptureLock
          elapsedMs={recorder.elapsedMs}
          level={recorder.level}
          micLabel={recorder.micLabel}
          onUnlock={() => setUnlocked(true)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  selectionBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    // Clear of the gesture bar, the same reason the pocket-mic switch is.
    paddingBottom: spacing.xl,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  selectionText: { flex: 1 },
  selectionCount: { color: colors.text, fontSize: 15, fontWeight: "600" },
  selectionHint: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  selectionCancel: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  selectionCancelText: { color: colors.textMuted, fontSize: 14 },
  mergeButton: {
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  mergeButtonOff: { opacity: 0.4 },
  // Same shape as Merge so they read as one row of choices, in the recording
  // red so the destructive one is never the button reached for by muscle memory.
  deleteButton: {
    backgroundColor: colors.recording,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  mergeButtonText: { color: colors.text, fontSize: 15, fontWeight: "600" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
  },
  brand: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  // The brand mark (assets/brand-mark.png, derived from the repo logo), tinted
  // to the theme so its baked-in ink never fights the dark surface. Width and
  // height keep the SVG's 845:696 aspect.
  brandMark: { width: 29, height: 24, tintColor: colors.text },
  gear: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
  },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  settings: { paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  settingsText: { color: colors.textMuted, fontSize: 14 },
  pressed: { opacity: 0.6 },
  micNote: { color: colors.warn, fontSize: 11, textAlign: "center" },
  filterBanner: {
    backgroundColor: colors.surfaceDeep,
    borderWidth: 1,
    borderColor: colors.warn,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  filterBannerText: { color: colors.warn, fontSize: 12, textAlign: "center" },
  controls: { paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: spacing.md },
  error: { color: colors.bad, fontSize: 12 },
  notice: { color: colors.warn, fontSize: 12 },
  list: { paddingHorizontal: spacing.lg, paddingBottom: pageEnd, gap: spacing.sm },
  empty: { paddingTop: spacing.xl, gap: spacing.sm, alignItems: "center" },
  emptyTitle: { color: colors.textMuted, fontSize: 15, fontWeight: "600" },
  emptyTitleBad: { color: colors.bad, fontSize: 16, fontWeight: "700" },
  emptyBody: { color: colors.textFaint, fontSize: 13, textAlign: "center", maxWidth: 260 },
});
