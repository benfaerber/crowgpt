/**
 * Folding several recordings of one event into a single capture.
 *
 * The use case is a stop-start field session: record, stop, the crow caws
 * again, record, stop. That is one event and the corpus holds it as four
 * captures, so anything counting events counts four and the context and counts
 * have to be entered four times.
 *
 * The joined audio is written to disk (see platform/writeMergedAudio). It began
 * as a view assembled on read, which was right for uploading and wrong for the
 * app: playback, the waveform and the normaliser all hand a file:// URI to the
 * OS, so a capture with no file behind it showed a player that never loaded.
 *
 * The parts stay on disk exactly as recorded either way, which is the property
 * that mattered — "destroy the originals" is a statement about the capture
 * *list*, not about the audio. The recordings survive, so a mis-tapped
 * selection cannot cost one.
 *
 * Ordering is by `recordedAt` rather than by selection or by id: the whole
 * point is to reconstruct a timeline, and the order the recordist happened to
 * tap in says nothing about when the birds called.
 */

/** Silence inserted between consecutive parts.
 *
 * Butt-joining would put the end of one caw hard against the start of the next
 * and read as a single continuous vocalisation to anything measuring gaps —
 * and within-bout spacing is a real signal (experiment 0003 measured 0.48 s for
 * alarm against 0.77 s for call). A gap longer than any natural spacing keeps
 * the join from being mistaken for one.
 *
 * It does not attempt to represent the true elapsed time. Twelve minutes of
 * silence between two ten-second recordings is a worse lie than a short pause:
 * it triples the file, and every offset in it would still be wrong by however
 * long the recordist took to press the button.
 */
export const MERGE_GAP_SEC = 3;

/**
 * The longest silence allowed between two consecutive parts.
 *
 * A merge says "these are one event". Recordings an hour apart are not, and the
 * merged capture would carry a single set of counts, one distance band and one
 * observer role over birds that had long since moved — metadata that reads as
 * observed when it was inherited.
 *
 * Measured between the *end* of one part and the start of the next, so a long
 * recording does not count against the bird that follows it. An hour is well
 * past any stop-start session and well short of a morning and an afternoon,
 * which is the confusion worth refusing.
 */
export const MERGE_MAX_APART_SEC = 3600;

export interface MergePart {
  uuid: string;
  recordedAt: string;
  durationMs: number;
  sampleRate: number;
  channels: number;
  audioPath: string;
}

export interface PlacedPart extends MergePart {
  /** Where this part begins in the merged timeline. */
  offsetMs: number;
}

export interface MergePlan {
  parts: PlacedPart[];
  gapMs: number;
  totalMs: number;
  /** The part the merged capture inherits its metadata from — the earliest. */
  source: PlacedPart;
}

export class MergeRefused extends Error {}

/**
 * Where each part lands on the merged timeline.
 *
 * Refuses rather than coerces. Parts recorded at different sample rates cannot
 * be concatenated without resampling, and a merge that silently resampled would
 * change the audio the recordist trusted us to keep — the one thing this
 * feature exists to avoid.
 */
export function planMerge(parts: MergePart[], gapSec: number = MERGE_GAP_SEC): MergePlan {
  if (parts.length < 2) {
    throw new MergeRefused("a merge needs at least two captures");
  }

  const ordered = [...parts].sort((a, b) =>
    a.recordedAt === b.recordedAt
      ? a.uuid.localeCompare(b.uuid)   // deterministic, not arbitrary
      : a.recordedAt.localeCompare(b.recordedAt));

  const { sampleRate, channels } = ordered[0];
  const mismatch = ordered.find((p) => p.sampleRate !== sampleRate || p.channels !== channels);
  if (mismatch) {
    throw new MergeRefused(
      `captures differ in format (${sampleRate} Hz/${channels}ch vs ` +
      `${mismatch.sampleRate} Hz/${mismatch.channels}ch) — merging would mean resampling`);
  }

  // Checked before anything is placed, so the message can name the real gap
  // rather than an offset in a timeline that should not exist.
  for (let i = 1; i < ordered.length; i += 1) {
    const previous = ordered[i - 1];
    const endedAt = Date.parse(previous.recordedAt) + previous.durationMs;
    const apartSec = (Date.parse(ordered[i].recordedAt) - endedAt) / 1000;
    if (apartSec > MERGE_MAX_APART_SEC) {
      const hours = (apartSec / 3600).toFixed(1);
      throw new MergeRefused(
        `${previous.uuid} and ${ordered[i].uuid} are ${hours} hours apart — a merge ` +
        `says they are one event, and its counts and distance would be inherited ` +
        `over birds that had moved`);
    }
  }

  const gapMs = Math.round(gapSec * 1000);
  let offsetMs = 0;
  const placed: PlacedPart[] = ordered.map((part, i) => {
    const at = offsetMs;
    offsetMs += part.durationMs + (i < ordered.length - 1 ? gapMs : 0);
    return { ...part, offsetMs: at };
  });

  return { parts: placed, gapMs, totalMs: offsetMs, source: placed[0] };
}

/**
 * Move a time inside one part onto the merged timeline.
 *
 * Labels, context events and sightings all carry offsets that only mean
 * anything within their own file. A fresh analysis regenerates *detections*,
 * which are the model's guesses and re-derivable — it does not regenerate
 * these, which are the only human ground truth in the corpus. They are moved
 * arithmetically instead, because the plan already knows where each part sits.
 */
export function rebase(plan: MergePlan, partUuid: string, seconds: number): number {
  const part = plan.parts.find((p) => p.uuid === partUuid);
  if (!part) throw new MergeRefused(`${partUuid} is not part of this merge`);
  return seconds + part.offsetMs / 1000;
}
