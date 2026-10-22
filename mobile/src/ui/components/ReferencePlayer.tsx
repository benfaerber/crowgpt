import { useAudioPlayer } from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AppServices } from "../../app/AppServices";
import { log } from "../../app/Log";
import type { LabelRecord } from "../../domain/labels";

/** A second of run-up, matching the labelling deck. */
const LEAD_IN_SEC = 1;
/** Long enough to hear the call and not the next one. */
const PLAY_SEC = 3;

export interface Reference {
  label: LabelRecord;
  uri: string;
}

/**
 * Play back a call already decided, to compare against one in hand.
 *
 * The field question this answers: "this was marked an alarm call, and the new
 * one sounds like it — same thing?" Answering it meant remembering what a
 * previous decision sounded like, which is not something anyone can do reliably
 * across a fortnight of recordings.
 *
 * Everything it needs is already on the phone. The labels are local until they
 * sync, and the audio never leaves — so this works with no signal, which is
 * where the question actually gets asked. Nothing is fetched and nothing is
 * cached; the reference library is the corpus already sitting there.
 *
 * One player, re-pointed per example, rather than one per row: a screen holding
 * a dozen audio players to play one of them is a memory cost for nothing.
 */
export function useReferencePlayer(services: AppServices) {
  const player = useAudioPlayer(null);
  const stopAt = useRef<number | undefined>(undefined);
  const [playing, setPlaying] = useState<string | undefined>();

  useEffect(() => {
    const timer = setInterval(() => {
      if (stopAt.current === undefined) return;
      if (player.currentTime >= stopAt.current) {
        player.pause();
        stopAt.current = undefined;
        setPlaying(undefined);
      }
    }, 100);
    return () => clearInterval(timer);
  }, [player]);

  /** Every example of this call type the phone can actually play. */
  const examplesFor = useCallback(
    async (callType: string, limit = 5): Promise<Reference[]> => {
      const labels = await services.labels.byCallType(callType, limit);
      const out: Reference[] = [];
      for (const label of labels) {
        const capture = await services.repository.get(label.captureUuid);
        // A label whose recording is gone — restored elsewhere, or deleted —
        // is not an example of anything.
        if (!capture?.audioPath) continue;
        out.push({
          label,
          uri: capture.audioPath.startsWith("file://")
            ? capture.audioPath
            : `file://${capture.audioPath}`,
        });
      }
      return out;
    },
    [services],
  );

  const play = useCallback(
    async (reference: Reference) => {
      const from = Math.max(0, reference.label.startSec - LEAD_IN_SEC);
      // Boosted like everything else played back, and here for the sharpest
      // reason: this is the side-by-side comparison. Judging a new call against
      // an old one where only one of them is audible is not a comparison.
      //
      // Resolved before anything else happens, because the seek belongs to the
      // source: replacing after seeking rewinds to the start, which is a call
      // played from the wrong place with nothing on screen to say so.
      const uri = services.settings.normalizePlayback
        ? await services.normalized
            .of(reference.uri)
            .then((louder) => louder.uri)
            .catch((failure) => {
              // Falling back to the quiet original is right; doing it with no
              // trace made a broken normaliser look like a quiet recording.
              log.warn("playback", "normalisation failed for a reference clip", failure);
              return reference.uri;
            })
        : reference.uri;

      player.replace({ uri });
      await player.seekTo(from);
      stopAt.current = Math.min(
        reference.label.endSec + LEAD_IN_SEC,
        from + PLAY_SEC + LEAD_IN_SEC,
      );
      player.play();
      setPlaying(reference.label.uuid);
    },
    [player, services],
  );

  const stop = useCallback(() => {
    player.pause();
    stopAt.current = undefined;
    setPlaying(undefined);
  }, [player]);

  return { examplesFor, play, stop, playing };
}
