import type { CaptureRecord } from "./types";

/**
 * What still needs somebody to say what is in it.
 *
 * Labelling is the only thing in this project that cannot be recovered later.
 * A missed sync is re-run tomorrow; a missed label lives in the recordist's
 * memory of an event that happened once and fades within hours. A 6:55pm
 * recording on 2026-08-01 went unlabelled and was noticed the next day, which
 * is the failure this exists to prevent.
 *
 * Pure, because the whole design risk is in the rule rather than the screen: a
 * queue that lists things nobody will ever label is a queue that gets ignored
 * within a week, and then it is worse than nothing — it has trained the one
 * person who uses it to look past it.
 */


/**
 * How long a recording stays fresh in the recordist's head.
 *
 * Three days, and the unit is nights rather than hours on purpose: what erodes
 * a field memory is sleeping and doing other things, not the clock. "It was
 * Tuesday" is how somebody actually reaches for it.
 *
 * Not a deadline and nothing expires — a cold recording stays in the queue and
 * is still worth labelling. It is a warning about the QUALITY of the label that
 * can still be made: what survives at a week is the shape of the event, and the
 * details that made it worth recording are the first to go.
 */
export const MEMORY_DAYS = 3;

export type LabelFreshness = "fresh" | "cold";

/** Local midnight, so "days ago" counts nights rather than 24-hour blocks. */
function startOfLocalDay(at: Date): Date {
  return new Date(at.getFullYear(), at.getMonth(), at.getDate());
}

/**
 * Whole days between the recording and today, by local calendar.
 *
 * Local for the same reason `captureFilters` is: a recording made at 9am in
 * Salt Lake is 15:48Z and an evening one lands on the next UTC day, so counting
 * in UTC would age some recordings a day early and others a day late. The bug
 * would be intermittent and blamed on something else.
 */
export function daysSinceRecorded(
  capture: CaptureRecord,
  now: Date = new Date(),
): number {
  const then = startOfLocalDay(new Date(capture.recordedAt));
  const today = startOfLocalDay(now);
  return Math.max(0, Math.round((today.getTime() - then.getTime()) / 86_400_000));
}

/**
 * Whether this one can still be labelled from memory, or only from the audio.
 *
 * The distinction the queue exists to make visible: this morning's recording
 * and one from last week are both "unlabelled", and they are not the same job.
 * One is remembering; the other is listening to a file and inferring — which is
 * a weaker claim, and the corpus cannot tell them apart afterwards.
 */
export function labelFreshness(
  capture: CaptureRecord,
  now: Date = new Date(),
): LabelFreshness {
  return daysSinceRecorded(capture, now) > MEMORY_DAYS ? "cold" : "fresh";
}

/**
 * Why a capture is not in the queue, or that it is.
 *
 * Three outcomes rather than a boolean, because "labelled" and "there is
 * nothing here to label" are different facts about the recording and only one
 * of them says anything about crows. Collapsing them is how a corpus loses the
 * distinction between a quiet morning and an unexamined one.
 */
export type LabelState = "waiting" | "labelled" | "nothing-to-label";

export function labelState(
  capture: CaptureRecord,
  labelCount: number,
): LabelState {
  if (labelCount > 0) return "labelled";
  // Deliberately checked after the count: a capture somebody dismissed and then
  // labelled anyway is labelled, and the dismissal was simply wrong.
  if (capture.nothingToLabelAt !== undefined) return "nothing-to-label";
  return "waiting";
}

/**
 * Whether this capture belongs in the queue at all.
 *
 * Scoped to ★ Keep, which is the flag that already separates a real field
 * recording from the seeded archive clips and test uploads that dominate the
 * corpus. Without that scope the queue opens onto a hundred recordings nobody
 * intends to label and is dead on arrival — see the file comment.
 *
 * A merged capture's parts are excluded: the merge is the recording now, and
 * labelling both would put the same call in the corpus twice.
 */
export function needsLabelling(
  capture: CaptureRecord,
  labelCount: number,
): boolean {
  if (!capture.keep) return false;
  if (capture.mergedInto !== undefined) return false;
  return labelState(capture, labelCount) === "waiting";
}

/**
 * The queue: newest first.
 *
 * Newest first is the entire point and not a default carried over from the
 * list. What makes a label good is how recently the recordist watched the thing
 * happen, so the recording made an hour ago is worth more attention than the
 * one from Tuesday — and if only one gets done today it should be that one.
 */
export function labelQueue(
  captures: readonly CaptureRecord[],
  counts: ReadonlyMap<string, number>,
): CaptureRecord[] {
  return captures
    .filter((capture) => needsLabelling(capture, counts.get(capture.uuid) ?? 0))
    .sort((a, b) => b.recordedAt.localeCompare(a.recordedAt));
}
