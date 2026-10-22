import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import Feather from "@expo/vector-icons/Feather";

import type { AppServices } from "../../app/AppServices";
import type { DictationControl } from "../../app/recorderView";
import {
  describeDictationState,
  dictationLabel,
  type DictationRecord,
} from "../../domain/dictations";
import { describeRingCost } from "../../domain/dictationSession";
import { colors, radius, spacing } from "../theme";

/**
 * Spoken notes about this capture.
 *
 * The point of the feature: a label is made from the recordist's memory of an
 * event that happened once and fades within hours, and everything in
 * `label-set` comes from his answers. A note taken seconds afterwards is those
 * same answers before they go stale.
 *
 * The card is the home for playback, transcripts and deletion. It is not where
 * a note should usually be STARTED — reaching this screen is four taps and a
 * scroll while a crow is still doing something, which is why the list has a
 * one-tap way in as well.
 */
export function DictationCard({
  services,
  captureUuid,
  dictation,
  notes,
  onChanged,
}: {
  services: AppServices;
  captureUuid: string;
  dictation: DictationControl;
  notes: DictationRecord[];
  onChanged: () => void;
}) {
  const mine = dictation.captureUuid === captureUuid;
  const busy = mine && dictation.phase !== "idle";
  const recording = mine && dictation.phase === "recording";

  // The card's own clock. Deliberately not in the recorder context — that is
  // read by the whole screen, and a value ticking four times a second there
  // re-renders the player and the waveform with it.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!recording) return setElapsed(0);
    const timer = setInterval(
      () => setElapsed(Date.now() - dictation.startedAt), 250);
    return () => clearInterval(timer);
  }, [recording, dictation.startedAt]);

  const seconds = Math.floor(elapsed / 1000);
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  const cost = describeRingCost(dictation.ringLossMs);

  const confirmDelete = (note: DictationRecord) =>
    Alert.alert(
      "Delete this note?",
      note.serverId !== undefined
        ? "It has already been sent to the server — this only removes it from the phone."
        : "The recording is removed from this phone and cannot be recovered here.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: () => void services.deleteDictation(note.uuid).then(onChanged),
        },
      ],
    );

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>Spoken notes</Text>
        <Text style={styles.meta}>
          {notes.length === 0 ? "none yet" : `${notes.length}`}
        </Text>
      </View>

      {notes.map((note, index) => (
        <NoteRow
          key={note.uuid}
          note={note}
          index={index}
          onDelete={() => confirmDelete(note)}
        />
      ))}

      {dictation.error && mine ? (
        <Text style={styles.error}>{dictation.error}</Text>
      ) : null}

      {recording ? (
        <Pressable
          onPress={() => void dictation.stop()}
          accessibilityRole="button"
          style={({ pressed }) => [styles.stop, pressed && styles.pressed]}
        >
          <View style={styles.recordingRow}>
            <View style={styles.tally} />
            <Text style={styles.stopText}>{`Stop · ${clock}`}</Text>
          </View>
          {/* Said for the whole time the microphone is on his voice, because
              nothing else on the phone is being recorded while it is. */}
          <Text style={styles.stopHint}>
            The microphone is on your voice. Nothing else is being recorded.
          </Text>
        </Pressable>
      ) : busy ? (
        <View style={styles.working}>
          <ActivityIndicator size="small" color={colors.textMuted} />
          <Text style={styles.meta}>{PHASE_TEXT[dictation.phase]}</Text>
        </View>
      ) : (
        <>
          <Pressable
            onPress={() => void dictation.start(captureUuid)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.record, pressed && styles.pressed]}
          >
            <Feather name="mic" size={16} color={colors.accent} />
            <Text style={styles.recordText}>Record a note</Text>
          </Pressable>
          {/* The cost, before the tap rather than after. The number is what
              decides whether to wait: fifteen seconds of held past is worth
              protecting if the birds are active right now and worth nothing if
              they are not. */}
          {cost ? <Text style={styles.hint}>{cost}</Text> : null}
        </>
      )}
    </View>
  );
}

const PHASE_TEXT: Record<DictationControl["phase"], string> = {
  idle: "",
  closing: "Closing the rolling buffer…",
  recording: "",
  saving: "Saving the note…",
  reopening: "Reopening the buffer…",
};

/**
 * One note, with a player.
 *
 * No `useNormalized`: that exists because a field recording peaks near −30 dBFS
 * and needs +18 dB to be reviewable, and it writes a second copy of every file
 * into the cache to do it. Speech at arm's length needs neither.
 */
function NoteRow({
  note,
  index,
  onDelete,
}: {
  note: DictationRecord;
  index: number;
  onDelete: () => void;
}) {
  const player = useAudioPlayer({ uri: note.audioPath });
  const status = useAudioPlayerStatus(player);
  const playable = note.state === "ready";

  return (
    <View style={styles.note}>
      <View style={styles.noteHeader}>
        <Pressable
          onPress={() => (status.playing ? player.pause() : player.play())}
          disabled={!playable}
          accessibilityRole="button"
          accessibilityLabel={status.playing ? "Pause the note" : "Play the note"}
          style={({ pressed }) => [
            styles.play, !playable && styles.disabled, pressed && styles.pressed,
          ]}
        >
          <Feather
            name={status.playing ? "pause" : "play"}
            size={14}
            color={colors.text}
          />
        </Pressable>
        <View style={styles.noteText}>
          <Text style={styles.noteTitle}>{dictationLabel(note, index)}</Text>
          <Text style={styles.meta}>{describeDictationState(note)}</Text>
        </View>
        <Pressable
          onPress={onDelete}
          accessibilityRole="button"
          accessibilityLabel="Delete this note"
          hitSlop={8}
          style={({ pressed }) => [pressed && styles.pressed]}
        >
          <Feather name="trash-2" size={14} color={colors.textFaint} />
        </Pressable>
      </View>

      {/* Only once there is one. A machine's reading of his words, and the
          hedge belongs wherever it is shown — this is not testimony until
          somebody has read it and said so. */}
      {note.transcript ? (
        <>
          <Text style={styles.transcript} selectable>{note.transcript}</Text>
          <Text style={styles.hint}>
            Transcribed by machine — check any name, number or species before
            trusting it.
          </Text>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: 14, fontWeight: "700" },
  meta: { color: colors.textMuted, fontSize: 12 },
  hint: { color: colors.textFaint, fontSize: 11 },
  error: { color: colors.bad, fontSize: 12 },
  note: { gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  noteHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  noteText: { flex: 1 },
  noteTitle: { color: colors.text, fontSize: 13, fontWeight: "600" },
  play: {
    width: 30, height: 30, borderRadius: 15,
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surfaceDeep,
  },
  transcript: { color: colors.text, fontSize: 13, lineHeight: 19 },
  record: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: spacing.sm, borderWidth: 1, borderColor: colors.accent,
    borderRadius: radius.sm, paddingVertical: spacing.sm,
  },
  recordText: { color: colors.accent, fontSize: 14, fontWeight: "700" },
  stop: {
    gap: spacing.xs, backgroundColor: colors.surfaceDeep,
    borderRadius: radius.sm, padding: spacing.sm, alignItems: "center",
  },
  recordingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  tally: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.recording },
  stopText: { color: colors.recording, fontSize: 15, fontWeight: "700" },
  stopHint: { color: colors.textMuted, fontSize: 11, textAlign: "center" },
  working: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  disabled: { opacity: 0.4 },
  pressed: { opacity: 0.7 },
});
