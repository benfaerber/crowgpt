import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";


import type { AppServices } from "../app/AppServices";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAnalysis } from "../app/useAnalysis";
import { useLocalEnvelope } from "../app/useLocalEnvelope";
import type { FamilyRecord } from "../domain/families";
import type { CaptureRecord } from "../domain/types";
import { newClientUuid } from "../domain/ids";
import { deviceRandomBytes } from "../platform/random";
import { needsDescriptionPush } from "../domain/revision";
import { CapturePlayer } from "./components/CapturePlayer";
import { CaptureVideo } from "./components/CaptureVideo";
import { DescriptionEditor } from "./components/DescriptionEditor";
import { DictationCard } from "./components/DictationCard";
import { KeyboardAwareScroll } from "./components/KeyboardAwareScroll";
import { GuessEditor } from "./components/GuessEditor";
import { FamilyPicker } from "./components/FamilyPicker";
import { DistancePicker } from "./components/DistancePicker";
import { GroupComposition } from "./components/GroupComposition";
import { ObserverRolePicker } from "./components/ObserverRolePicker";
import { describePlace, mayShowCoords } from "../domain/location";
import { LabelSummary } from "./components/LabelSummary";
import { daysSinceRecorded, labelFreshness } from "../domain/labelQueue";
import { useRecorderView } from "../app/RecorderContext";
import type { DictationRecord } from "../domain/dictations";
import { ManualLabel } from "./components/ManualLabel";
import { NameEditor } from "./components/NameEditor";
import { captureId, colors, formatBytes, formatDuration, formatRecordedAt, pageEnd, radius, spacing, syncBadge } from "./theme";

export function CaptureDetailScreen({
  services,
  capture,
  onBack,
  onDelete,
  onUnmerge,
  onViewOnMap,
  onDescribe,
  onCreateFamily,
  onLabel,
}: {
  services: AppServices;
  capture: CaptureRecord;
  onBack: () => void;
  onDelete: (uuid: string) => void;
  /** Return a merged capture's original recordings to the list. */
  onUnmerge: (uuid: string) => void;
  onViewOnMap: (capture: CaptureRecord) => void;
  onDescribe: (uuid: string, body: string) => Promise<CaptureRecord>;
  onCreateFamily: () => void;
  /** Opens the one-call-at-a-time labelling deck. */
  onLabel: () => void;
}) {
  const [current, setCurrent] = useState(capture);
  const scroller = useRef<ScrollView>(null);
  // Where "mark a call by ear" lives. The label card scrolls here when there is
  // no deck to open, instead of opening an empty one.
  const manualLabelY = useRef(0);
  const analysis = useAnalysis(services, current);

  /**
   * By-ear labels for the timeline. Marking a call the analyzer missed used
   * to vanish into the labels store — counted by the summary, invisible on
   * the very timeline that exists to show where calls sit.
   */
  const [earLabels, setEarLabels] = useState<
    { startSec: number; endSec: number; callType: string }[]
  >([]);
  const reloadEarLabels = useCallback(async () => {
    const rows = await services.labels.forCapture(current.uuid);
    setEarLabels(rows.filter((row) => row.fromDetection !== true));
  }, [services, current.uuid]);
  useEffect(() => {
    void reloadEarLabels();
  }, [reloadEarLabels]);
  const local = useLocalEnvelope(services, current);
  const [families, setFamilies] = useState<FamilyRecord[]>([]);

  useEffect(() => {
    void services.families.list().then(setFamilies);
  }, [services]);
  const [seekRequest, setSeekRequest] = useState<{ seconds: number; nonce: number }>();
  // Folded by default — it is reference material — except when the capture went
  // through a microphone it did not ask for, which is exactly the fact this
  // screen must not be able to hide behind a tap.
  const [detailsOpen, setDetailsOpen] = useState(capture.inputHonoured === false);
  // Marking a call by ear needs the playhead outside the player — and the
  // video card follows it, so `playing` rides along.
  const [playhead, setPlayhead] = useState({ seconds: 0, duration: 0, playing: false });

  const spanSec = analysis.duration ?? local.durationSec ?? current.durationMs / 1000;
  const crop = { startSec: current.cropStartSec, endSec: current.cropEndSec };
  const cropped = crop.startSec !== undefined || crop.endSec !== undefined;

  // One second of lead-in: a call is easier to recognise with the moment before
  // it, and landing exactly on the onset usually clips the start.
  const skipToCall = (startSec?: number) =>
    setSeekRequest({ seconds: Math.max(0, (startSec ?? 0) - 1), nonce: Date.now() });

  const setCrop = async (patch: { cropStartSec?: number; cropEndSec?: number }) => {
    const updated = await services.repository.update(current.uuid, patch);
    services.setCrop(updated.audioPath, {
      startSec: updated.cropStartSec,
      endSec: updated.cropEndSec,
    });
    setCurrent(updated);
  };
  const synced = current.syncState === "synced";
  const badge = syncBadge(current);
  const id = captureId(current);
  const recorder = useRecorderView();
  // Reloaded whenever one is made or deleted; the recorder's phase returning to
  // idle is the signal that a note has finished being written.
  const [notes, setNotes] = useState<DictationRecord[]>([]);
  const reloadNotes = useCallback(
    () => void services.dictations.forCapture(current.uuid).then(setNotes),
    [services, current.uuid]);
  useEffect(reloadNotes, [reloadNotes, recorder.dictation.phase]);
  // And when a sync ends, because that is when a transcript lands. Without
  // this the card goes on saying "transcript arrives on the next sync" over a
  // transcript already sitting in the store.
  useEffect(
    () => services.syncEngine.onRunningChanged((running) => {
      if (!running) reloadNotes();
    }),
    [services, reloadNotes]);

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={({ pressed }) => [pressed && styles.pressed]}>
          <Text style={styles.back}>‹ Captures</Text>
        </Pressable>
        <Pressable
          onPress={async () => setCurrent(await services.repository.update(current.uuid, { keep: !current.keep }))}
          style={({ pressed }) => [styles.keep, current.keep && styles.keepOn, pressed && styles.pressed]}
        >
          <Text style={[styles.keepText, current.keep && styles.keepTextOn]}>
            {current.keep ? "★ Keep" : "☆ Keep"}
          </Text>
        </Pressable>
        {/* Same badge as the list row, from one function. This screen used to
            compute it itself and did not know about "Edited" — so the screen you
            are on when you make an edit was the one screen that kept saying
            "Synced", which is how a working sync looks broken. */}
        <View style={[styles.badge, { borderColor: badge.color }]}>
          <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
        </View>
      </View>

      <KeyboardAwareScroll ref={scroller} contentContainerStyle={styles.body}>
        {/* Beside the timestamp rather than buried under "more", which is where
            it was: this is the capture's NAME everywhere outside the phone, and
            the reason to want it on screen is to type it into something else.
            A capture that has never synced has no id at all, and says so — the
            blank it used to leave read as a missing number. */}
        <View style={styles.identity}>
          <Text style={styles.when}>{formatRecordedAt(current.recordedAt)}</Text>
          <Text style={id ? styles.id : styles.idNone}>{id ?? "no id until synced"}</Text>
        </View>

        <CapturePlayer
          services={services}
          config={services.config}
          audioPath={current.audioPath}
          fallbackMs={current.durationMs}
          waveform={analysis.waveform.length > 0 ? analysis.waveform : local.peaks}
          calls={analysis.calls}
          earLabels={earLabels}
          analyzedDuration={analysis.duration ?? local.durationSec}
          crop={crop}
          onCropChange={(next) => setCrop({ cropStartSec: next.startSec, cropEndSec: next.endSec })}
          seekRequest={seekRequest}
          onPosition={useCallback(
            (seconds: number, duration: number, playing: boolean) =>
              setPlayhead({ seconds, duration, playing }),
            [],
          )}
        />

        {cropped ? (
          <View style={styles.cropRow}>
            <Text style={styles.hint}>
              Uploading {formatDuration(
                ((crop.endSec ?? spanSec) - (crop.startSec ?? 0)) * 1000,
              )} of {formatDuration(spanSec * 1000)} — the recording on the phone is
              untouched{current.videoPath ? ", and video uploads whole" : ""}.
            </Text>
            <Pressable
              onPress={() => setCrop({ cropStartSec: undefined, cropEndSec: undefined })}
              style={({ pressed }) => [styles.resetCrop, pressed && styles.pressed]}
            >
              <Text style={styles.actionText}>Reset</Text>
            </Pressable>
          </View>
        ) : (
          <Text style={styles.hint}>Drag the amber handles to trim before uploading.</Text>
        )}

        {current.videoPath ? (
          <CaptureVideo
            uri={current.videoPath}
            bytes={current.videoBytes}
            preRollSec={current.preRollSec}
            audioDurationSec={current.durationMs / 1000}
            seekRequest={seekRequest}
            follow={{ seconds: playhead.seconds, playing: playhead.playing }}
          />
        ) : null}

        <View>
          <NameEditor
            value={current.name}
            onSave={async (name) =>
              setCurrent(await services.repository.update(current.uuid, { name }))
            }
          />

          <View style={styles.spacer} />

          {/* Directly under the name, because they answer the same question at
              two lengths — "what is this recording" — and writing one usually
              means writing the other. Everything below is a decision about the
              capture rather than a description of it. */}
          <DescriptionEditor
            value={current.description}
            pendingSync={needsDescriptionPush(current)}
            onSave={async (body) => setCurrent(await onDescribe(current.uuid, body))}
          />

          <View style={styles.spacer} />

          {/* Right under the description, because it is the natural next
              sentence — and a separate field rather than more of the same box,
              because "what happened" and "what I think it meant" have to stay
              distinguishable for any of this to be worth analysing. */}
          <GuessEditor
            value={current.behaviorGuess}
            onSave={async (behaviorGuess) =>
              setCurrent(
                await services.repository.update(current.uuid, {
                  behaviorGuess: behaviorGuess || undefined,
                }),
              )
            }
          />

          <View style={styles.spacer} />

          <FamilyPicker
            families={families}
            selectedUuid={current.familyUuid}
            onSelect={async (familyUuid) =>
              setCurrent(await services.repository.update(current.uuid, { familyUuid }))
            }
            onCreateNew={onCreateFamily}
          />

          <View style={styles.spacer} />

          {/* Beside the observer role: both describe the conditions of the
              recording rather than its content. */}
          {/* Beside distance on purpose: ageing a crow needs the eye and the
              gape, so how close you got is what says whether the split is
              credible. */}
          <GroupComposition
            adults={current.adultCount}
            juveniles={current.juvenileCount}
            unaged={current.unagedCount}
            onChange={async (field, value) =>
              setCurrent(await services.repository.update(current.uuid, { [field]: value }))
            }
          />

          <View style={styles.spacer} />

          {/* Both answers below are remembered as the next capture's
              pre-selection — choosing "Not said" is remembered too, so a
              cleared answer does not resurrect on the next recording. */}
          <DistancePicker
            value={current.distanceBand}
            onChange={async (distanceBand) => {
              setCurrent(await services.repository.update(current.uuid, { distanceBand }));
              services.applySettings({
                ...services.settings,
                lastDistanceBand: distanceBand ?? "",
              });
            }}
          />

          <View style={styles.spacer} />

          <ObserverRolePicker
            roles={services.config.observer_roles}
            selected={current.observerRole}
            onSelect={async (observerRole) => {
              setCurrent(await services.repository.update(current.uuid, { observerRole }));
              services.applySettings({
                ...services.settings,
                lastObserverRole: observerRole ?? "",
              });
            }}
          />

          {/* Every card in this group is spaced the same way, so they read as
              one column of controls rather than a pile of unrelated panels. */}
          <View style={styles.spacer} />

          {/* Beside the written description, because a note IS the description
              spoken — the same account, taken while it is still fresh rather
              than at a desk hours later. */}
          <DictationCard
            services={services}
            captureUuid={current.uuid}
            dictation={recorder.dictation}
            notes={notes}
            onChanged={reloadNotes}
          />

          <View style={styles.spacer} />

          <LabelSummary
            services={services}
            captureUuid={current.uuid}
            calls={analysis.calls}
            silent={current.silentConfirmedAt !== undefined}
            onPress={onLabel}
            onMarkByEar={() =>
              scroller.current?.scrollTo({
                y: Math.max(0, manualLabelY.current - 24),
                animated: true,
              })
            }
          />

          {/* THE WAY OUT OF THE QUEUE, and the queue does not work without it.
              Some recordings should never be labelled — a test upload, a seeded
              clip, a walk that caught only traffic — and a queue that lists them
              forever is one nobody opens after a week.

              Only offered for a kept recording, because only those are in the
              queue, and it says which claim it is making: this is about the
              file, not about the birds. "Listened, no crow calls" is the other
              button and a genuinely different fact — it is the denominator. */}
          {/* Said where the label is actually made, not only on the row. It
              states the age and stops there: whether the morning is still in
              your head is something only you know, and an app that announces
              "context lost" would be overruling you about your own memory. The
              useful half is the instruction — write what you still trust. */}
          {current.keep && labelFreshness(current) === "cold" ? (
            <>
              <View style={styles.spacer} />
              <View style={[styles.card, styles.stale]}>
                <Text style={styles.staleText}>
                  {`Recorded ${daysSinceRecorded(current)} days ago.`}
                </Text>
                <Text style={styles.skipHint}>
                  Label what you still remember and leave the rest — a guess
                  entered now is indistinguishable from something you watched.
                </Text>
              </View>
            </>
          ) : null}

          {current.keep ? (
            <>
              <View style={styles.spacer} />
              <Pressable
                onPress={async () =>
                  setCurrent(await services.repository.update(current.uuid, {
                    nothingToLabelAt: current.nothingToLabelAt
                      ? undefined
                      : new Date().toISOString(),
                  }))
                }
                style={({ pressed }) => [styles.card, styles.skip, pressed && styles.pressed]}
              >
                <Text style={styles.skipText}>
                  {current.nothingToLabelAt
                    ? "✓ Waved past — nothing here to label"
                    : "Nothing here to label"}
                </Text>
                <Text style={styles.skipHint}>
                  {current.nothingToLabelAt
                    ? "Tap to put it back in the queue."
                    : "Takes it out of the label queue. Not a claim about crows — "
                      + "for that, mark it listened and silent."}
                </Text>
              </Pressable>
            </>
          ) : null}

          {/* Marking stays here rather than in the deck: finding a call the
              analyzer missed means scrubbing the whole recording, which needs
              the waveform and the playhead above. The deck is for deciding
              about spans that are already known. */}
          <View
            style={styles.spacer}
            onLayout={(event) => (manualLabelY.current = event.nativeEvent.layout.y)}
          />
          <ManualLabel
            config={services.config}
            playheadSec={playhead.seconds}
            duration={playhead.duration || spanSec}
            onCreate={async (span) => {
              await services.addLabel({
                uuid: newClientUuid(deviceRandomBytes),
                captureUuid: current.uuid,
                ...span,
                fromDetection: false,
              });
              await reloadEarLabels();
              setCurrent((await services.repository.get(current.uuid)) ?? current);
            }}
          />

        </View>

        {/* Below everything that gets used, because this gets referred to: the
            file's own facts, folded to their headline numbers. */}
        <View style={styles.card}>
          <Pressable
            onPress={() => setDetailsOpen((open) => !open)}
            style={({ pressed }) => [styles.detailsToggle, pressed && styles.pressed]}
          >
            <Text style={styles.fieldValue}>
              {formatDuration(current.durationMs)} · {formatBytes(current.bytes)} ·{" "}
              {current.sampleRate} Hz
            </Text>
            <Text style={styles.fieldLabel}>{detailsOpen ? "less ▾" : "more ▸"}</Text>
          </Pressable>
          {detailsOpen ? (
            <>
              {current.trigger === "auto" ? (
                <Field
                  label="Started by"
                  value="the idle trigger — nobody was there"
                />
              ) : null}
              {current.inputDevice ? (
                <Field
                  label="Microphone"
                  value={describeInput(current.inputDevice, current.inputHonoured)}
                />
              ) : null}
              {current.preRollSec ? (
                <Field
                  label="Pre-roll"
                  value={`first ${current.preRollSec.toFixed(1)}s from the buffer`}
                />
              ) : null}
              <Field
                label="Location"
                value={describePlace(current, services.settings.locationPrecision) ?? "not recorded"}
              />
              {current.syncState !== "local" && (
                <Field
                  label="Uploaded"
                  value={`${formatBytes(current.uploadedBytes)} of ${formatBytes(current.bytes)}`}
                />
              )}
              {current.videoPath && (
                <Field
                  label="Video"
                  value={`${formatBytes(current.videoBytes ?? 0)}${
                    current.syncState === "synced"
                      ? ""
                      : ` · ${formatBytes(current.videoUploadedBytes ?? 0)} uploaded`
                  }`}
                />
              )}
            </>
          ) : null}
        </View>

        {/* Hidden with the coordinates rather than left pointing at a map of
            them: an exact pin reached from a screen that says "Utah, US" would
            undo the setting in one tap. */}
        {mayShowCoords(services.settings.locationPrecision, services.settings.censorCoords)
          && current.latitude !== undefined && current.longitude !== undefined && (
          <Pressable
            onPress={() => onViewOnMap(capture)}
            style={({ pressed }) => [styles.action, pressed && styles.pressed]}
          >
            <Text style={styles.actionText}>View on map</Text>
          </Pressable>
        )}

        {current.notes ? <Text style={styles.notes}>{current.notes}</Text> : null}

        {current.lastError ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorTitle}>Last sync failed</Text>
            <Text style={styles.errorBody}>{current.lastError}</Text>
            <Text style={styles.errorHint}>
              {current.attempts} attempt{current.attempts === 1 ? "" : "s"}. Tap Sync on the
              capture list to try again.
            </Text>
          </View>
        ) : null}

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Detected calls</Text>
            {analysis.working ? <ActivityIndicator size="small" color={colors.accent} /> : null}
          </View>

          {/* The verdict on an unattended capture, in words. The trigger is a
              level gate that a siren can trip, and BirdNET after upload is the
              validation half of the design — so an auto capture says plainly
              which way the check came out. "No crow" is only claimed when not
              even a 0.10 candidate turned up: capture 88's real alarm call
              scored 0.183, so the deletion advice stays conservative and
              always asks for ears first. */}
          {(() => {
            if (current.trigger !== "auto" || !synced || analysis.working) return null;
            if (analysis.calls.length === 0) {
              if (analysis.duration === undefined) return null;
              return (
                <Text style={[styles.hint, { color: colors.textMuted }]}>
                  Auto capture, and no crow found — not even a low-confidence
                  candidate. Probably a false trigger (a car, a siren). Listen
                  once, then delete.
                </Text>
              );
            }
            const confident = analysis.calls.some((call) => !call.candidate);
            return confident ? (
              <Text style={[styles.hint, { color: colors.good }]}>
                Auto capture, and the trigger was right — BirdNET hears a crow.
              </Text>
            ) : (
              <Text style={[styles.hint, { color: colors.warn }]}>
                Auto capture with only low-confidence candidates. A real call
                can score this low — ears before delete.
              </Text>
            );
          })()}

          {/* Said plainly rather than shown silently. These are real results
              and worth having in a field with no signal, but the server has not
              confirmed them just now, and the difference matters if the capture
              has been re-analyzed since. */}
          {analysis.cachedAt ? (
            <Text style={styles.hint}>
              Server not reachable — showing the analysis from{" "}
              {formatRecordedAt(analysis.cachedAt)}.
            </Text>
          ) : null}

          {!synced ? (
            <Text style={styles.hint}>
              This capture is still only on the phone. Sync it and the server will analyze it.
            </Text>
          ) : analysis.calls.length === 0 ? (
            <View style={styles.gap}>
              <Text style={styles.hint}>
                {analysis.working
                  ? `Analyzing… (${analysis.status ?? "queued"})`
                  : "Nothing detected yet."}
              </Text>
              <Pressable
                onPress={analysis.requestAnalysis}
                disabled={analysis.working}
                style={({ pressed }) => [
                  styles.action,
                  analysis.working && styles.actionDisabled,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.actionText}>Analyze</Text>
              </Pressable>
            </View>
          ) : (
            analysis.calls.map((call, index) => (
              <View key={index} style={styles.call}>
                <View style={styles.callHeader}>
                  <Text style={styles.callSpecies}>{call.species}</Text>
                  <Text style={styles.callTime}>
                    {formatSpan(call.start_sec, call.end_sec)}
                  </Text>
                </View>
                {/* 0.78 rather than 78%, matching the dashboard, the analyzer
                    and every experiment. The percentage was not just an
                    inconsistency: it reads as "78% likely to be right", and a
                    BirdNET score is not a calibrated probability. What
                    calibration exists is per species and call type, and it
                    lives in the reliability figures, not in this number. */}
                <Text style={styles.callMeta}>
                  {call.call_type ?? "call type unknown"}
                  {typeof call.confidence === "number"
                    ? ` · ${call.confidence.toFixed(2)}`
                    : ""}
                </Text>
                <Pressable
                  onPress={() => skipToCall(call.start_sec)}
                  style={({ pressed }) => [styles.skipToCall, pressed && styles.pressed]}
                >
                  <Text style={styles.skipToCallText}>Skip to call</Text>
                </Pressable>
              </View>
            ))
          )}

          {analysis.error ? <Text style={styles.errorBody}>{analysis.error}</Text> : null}
        </View>

        {current.mergedFrom ? (
          // The way back the merge screen promises: the original recordings
          // are untouched on disk, so this only forgets the joined copy.
          <Pressable
            onPress={() => onUnmerge(current.uuid)}
            style={({ pressed }) => [styles.unmerge, pressed && styles.pressed]}
          >
            <Text style={styles.unmergeText}>
              Un-merge — return the {current.mergedFrom.length} original recordings
            </Text>
          </Pressable>
        ) : null}

        <Pressable
          onPress={() => onDelete(current.uuid)}
          style={({ pressed }) => [styles.destructive, pressed && styles.pressed]}
        >
          <Text style={styles.destructiveText}>
            {synced ? "Delete from phone" : "Delete (not yet synced)"}
          </Text>
        </Pressable>
      </KeyboardAwareScroll>
    </View>
  );
}

/** A detection with no timing is still worth showing; it just has no span. */
function formatSpan(start?: number, end?: number): string {
  if (typeof start !== "number" || typeof end !== "number") return "";
  return `${start.toFixed(0)}–${end.toFixed(0)}s`;
}

/**
 * Which microphone this capture actually went through.
 *
 * Spelled out rather than shown as a raw constant, because the thing worth
 * noticing is not the device name but that a Bluetooth route means narrowband,
 * speech-processed audio — a recording that is far less useful for training and
 * whose only other symptom is sounding vaguely wrong.
 */
function describeInput(device: string, honoured?: boolean): string {
  const name =
    device === "BUILTIN_MIC"
      ? "phone microphone"
      : device === "BLUETOOTH_SCO"
        ? "Bluetooth headset — low bandwidth"
        : device.toLowerCase().replace(/_/g, " ");
  return honoured === false ? `${name} (requested mic refused)` : name;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
  },
  back: { color: colors.accent, fontSize: 16 },
  pressed: { opacity: 0.6 },
  badge: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  badgeText: { fontSize: 11, fontWeight: "700" },
  body: { paddingHorizontal: spacing.lg, paddingBottom: pageEnd, gap: spacing.md },
  skip: { gap: spacing.xs },
  stale: { gap: spacing.xs, borderLeftWidth: 3, borderLeftColor: colors.textFaint },
  staleText: { color: colors.textMuted, fontSize: 14, fontWeight: "600" },
  skipText: { color: colors.text, fontSize: 14, fontWeight: "600" },
  skipHint: { color: colors.textMuted, fontSize: 12 },
  identity: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: spacing.sm },
  id: { color: colors.text, fontFamily: "monospace", fontSize: 15, fontVariant: ["tabular-nums"] },
  idNone: { color: colors.textFaint, fontSize: 12 },
  when: { color: colors.text, fontSize: 20, fontWeight: "700" },
  notes: { color: colors.textMuted, fontSize: 12, fontStyle: "italic" },
  cropRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  resetCrop: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  keep: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginLeft: "auto",
    marginRight: spacing.sm,
  },
  keepOn: { borderColor: colors.warn },
  keepText: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  keepTextOn: { color: colors.warn },
  skipToCall: {
    marginTop: spacing.xs,
    alignSelf: "flex-start",
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  skipToCallText: { color: colors.text, fontSize: 11, fontWeight: "700" },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.xs },
  detailsToggle: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  field: { flexDirection: "row", justifyContent: "space-between" },
  fieldLabel: { color: colors.textMuted, fontSize: 13 },
  fieldValue: { color: colors.text, fontSize: 13, fontWeight: "600" },
  errorCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
    borderLeftWidth: 3,
    borderLeftColor: colors.bad,
  },
  errorTitle: { color: colors.bad, fontSize: 13, fontWeight: "700" },
  errorBody: { color: colors.textMuted, fontSize: 12 },
  errorHint: { color: colors.textFaint, fontSize: 11 },
  section: { gap: spacing.sm },
  sectionHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: "700" },
  gap: { gap: spacing.sm },
  spacer: { height: spacing.xs },
  hint: { color: colors.textFaint, fontSize: 13 },
  call: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: 2 },
  callHeader: { flexDirection: "row", justifyContent: "space-between" },
  callSpecies: { color: colors.text, fontSize: 14, fontWeight: "600" },
  callTime: { color: colors.textMuted, fontSize: 12, fontVariant: ["tabular-nums"] },
  callMeta: { color: colors.textMuted, fontSize: 12 },
  action: {
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  actionDisabled: { opacity: 0.4 },
  actionText: { color: colors.text, fontSize: 14, fontWeight: "700" },
  destructive: {
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  destructiveText: { color: colors.bad, fontSize: 14 },
  unmerge: {
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  unmergeText: { color: colors.textMuted, fontSize: 14 },
});
