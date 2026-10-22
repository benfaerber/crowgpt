/**
 * Captures that exist but have not been written down yet.
 *
 * Between the microphone closing and the row landing in the store there is a
 * gap of seconds — a GPS fix that has not arrived, a region being resolved, a
 * video file being finalized — and for the whole of it the recordist has made a
 * recording that nothing on screen can see. The list said "no captures yet"
 * over audio that was already safely on disk, which reads as a recording that
 * did not happen: the one thing this app must never appear to do.
 *
 * So a placeholder stands in the row's place until the row exists. It is
 * deliberately NOT a capture — nothing writes it to the database, nothing syncs
 * it, and a placeholder that never settles disappears with the process rather
 * than becoming a phantom row somebody has to explain later. It is a statement
 * about the app's own work in progress, and the store stays the single source
 * of truth for what was recorded.
 *
 * Pure, because "which placeholder settles when the row arrives" is a rule, and
 * a rule that leaks a stuck spinner into the list is checkable without a phone.
 */

export interface PendingCapture {
  /** Distinguishes concurrent placeholders. Not a capture uuid — see above. */
  id: string;
  /** Which button made it, so the row can say the right thing. */
  kind: "audio" | "video";
  /**
   * How long the recording is, once the file is closed.
   *
   * Known before the row exists — it comes back from the recorder with the
   * file — so the placeholder can state it rather than showing a blank where
   * the duration will be. A placeholder that already knows the length is much
   * harder to mistake for a hung one.
   */
  durationMs?: number;
}

export function addPending(
  current: readonly PendingCapture[],
  entry: PendingCapture,
): PendingCapture[] {
  return [...current, entry];
}

/**
 * Drop the placeholder its work has finished for.
 *
 * By id rather than by position, and tolerant of an id that is already gone:
 * settling runs from a `finally`, so a failed capture settles the same
 * placeholder its error path may already have cleared. Removing an absent id
 * has to be a no-op or the second call throws inside the very handler written
 * to guarantee the spinner goes away.
 */
export function settlePending(
  current: readonly PendingCapture[],
  id: string,
): PendingCapture[] {
  return current.filter((entry) => entry.id !== id);
}
