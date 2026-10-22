import type { NewCapture } from "./types";

/**
 * Audio found on disk with no capture pointing at it.
 *
 * Mirrors the native `OrphanCapture` without importing the module, so this
 * stays testable off a phone.
 */
export interface OrphanAudio {
  path: string;
  bytes: number;
  durationMs: number;
  sampleRate: number;
  /** Epoch millis from the file's mtime — the only record of when it happened. */
  modifiedAt: number;
}

/**
 * How short a recovered file has to be before it is not worth entering.
 *
 * A capture killed within a second of the button is almost certainly a misfire
 * rather than a call, and a list filling with half-second rows is a list nobody
 * reads. Recovered, not deleted: the file stays on disk either way.
 */
export const MIN_RECOVERABLE_MS = 1000;

/**
 * Turn abandoned audio into a capture the recordist can see.
 *
 * The honesty rules matter more than the mechanism here:
 *
 *   - `recordedAt` is derived by counting back from the file's mtime, the same
 *     arithmetic a healthy stop does from the wall clock. It is approximate and
 *     unavoidably so — the row that would have said when this started was never
 *     written.
 *   - the note says plainly that the app was killed and that the end is
 *     missing, because a recovered capture is *not* the same object as one that
 *     ended when somebody pressed stop, and a list that showed them
 *     identically would be lying by omission.
 *   - no location, no region, no input device. Those were known only to the
 *     process that died, and inventing them would put guesses in the corpus
 *     next to measurements.
 */
export function captureFromOrphan(
  orphan: OrphanAudio,
  ids: { uuid: string; mediaUuid: string },
): NewCapture {
  return {
    uuid: ids.uuid,
    mediaUuid: ids.mediaUuid,
    recordedAt: new Date(orphan.modifiedAt - orphan.durationMs).toISOString(),
    durationMs: orphan.durationMs,
    sampleRate: orphan.sampleRate,
    channels: 1,
    audioPath: orphan.path,
    bytes: orphan.bytes,
    notes:
      "Recovered after the app stopped mid-recording. The audio up to that "
      + "moment is here; the end of the recording was never written, and the "
      + "time is taken from the file rather than the clock.",
  };
}

/** Which orphans are worth entering, longest-lived question first. */
export function worthRecovering(orphans: OrphanAudio[]): OrphanAudio[] {
  return orphans.filter((orphan) => orphan.durationMs >= MIN_RECOVERABLE_MS);
}
