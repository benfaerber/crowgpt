import type { CaptureRecord } from "./types";

/**
 * Which edits the server needs to hear about again.
 *
 * A capture used to be finished the moment it synced: `pendingSync` selects
 * `local` and `failed`, so a description typed *after* the upload was never
 * looked at again and simply never arrived. There was no way to ask for it to
 * be re-sent — the Sync button had nothing to offer.
 *
 * So each capture carries a local revision that these fields bump, and a synced
 * revision recorded when a push succeeds. Ahead means owing. A counter rather
 * than a timestamp for the same reason the description compares text rather
 * than dates: a field phone's clock can be wrong, and a wrong clock must not be
 * able to strand an edit or re-send it forever.
 *
 * Deliberately excluded: everything the *sync* writes — server ids, byte
 * counts, attempts, sync state. Including those would make a sync dirty the
 * record it just cleaned, and it would never settle.
 */
export const SYNCED_FIELDS = [
  "name",
  "description",
  "notes",
  "keep",
  "familyUuid",
  "locationName",
  "latitude",
  "longitude",
  // Set at the desk far more often than in the moment. Without it here, the
  // edit re-syncs forever without ever landing — the same trap family tagging
  // fell into.
  "observerRole",
  "distanceBand",
  "adultCount",
  "juvenileCount",
  "unagedCount",
  "silentConfirmedAt",
  "nothingToLabelAt",
  "behaviorGuess",
] as const satisfies readonly (keyof CaptureRecord)[];

/**
 * Whether a patch changes anything the server holds a copy of.
 *
 * Compares values rather than trusting the presence of a key: screens routinely
 * write back a field they didn't change, and a re-sync per keystroke of an
 * unchanged form would be its own bug.
 *
 * Crop is *not* here. Re-cropping after the audio has landed would need the
 * corrected bytes re-uploaded under a fresh media id, which is a different
 * feature — the crop still applies normally to a capture that has not synced.
 */
export function isDirtyingChange(
  current: Pick<CaptureRecord, (typeof SYNCED_FIELDS)[number]>,
  patch: Partial<CaptureRecord>,
): boolean {
  return SYNCED_FIELDS.some(
    (field) => field in patch && !same(current[field], patch[field]),
  );
}

/** Undefined, null and "" all mean "nothing here" once a value round-trips SQLite. */
function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  return blank(a) && blank(b);
}

function blank(value: unknown): boolean {
  return value === undefined || value === null || value === "";
}

/** True when the phone holds edits the server has not accepted yet. */
export function hasUnsyncedEdits(capture: CaptureRecord): boolean {
  return (capture.localRevision ?? 0) > (capture.syncedRevision ?? 0);
}

/**
 * Whether the capture's description still owes the server something: never sent,
 * or edited since it last was.
 */
export function needsDescriptionPush(capture: CaptureRecord): boolean {
  const body = capture.description?.trim();
  if (!body || !capture.descriptionUuid) return false;
  return body !== capture.descriptionSyncedBody;
}
