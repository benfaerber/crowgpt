import type { CaptureRecord } from "./types";

/**
 * Narrowing the capture list.
 *
 * The corpus grows by a handful of recordings a day and most of it is seeded
 * clips and test uploads, so "the thing I recorded this morning" is several
 * screens down by the afternoon. Everything here is a *view* — nothing is
 * deleted, hidden permanently, or written back.
 *
 * Day boundaries are local, not UTC. A capture made at 9am in Salt Lake is
 * 15:48Z, and an evening recording is the *next* day in UTC — so a "today"
 * filter built on UTC would drop the morning's work some hours and include
 * yesterday's on others. The bug would be intermittent and blamed on sync.
 */

export type SortOrder = "newest" | "oldest";
export type DateRange = "all" | "today" | "week" | "month";

export interface CaptureView {
  order: SortOrder;
  range: DateRange;
  /** Only captures marked as real observations. */
  keptOnly: boolean;
  /**
   * Only kept recordings nobody has said anything about yet.
   *
   * The label queue. Not a date range or a sort — a different question about
   * the same list, and the only one whose answer decays: a label is made from
   * the recordist's memory of an event that happened once, and that fades
   * within hours. See domain/labelQueue.
   */
  unlabelledOnly: boolean;
}

export const DEFAULT_VIEW: CaptureView = {
  order: "newest",
  range: "all",
  keptOnly: false,
  unlabelledOnly: false,
};

export const RANGE_LABELS: Record<DateRange, string> = {
  all: "All",
  today: "Today",
  week: "7 days",
  month: "30 days",
};

/** Midnight this morning, in the phone's own timezone. */
function startOfLocalDay(now: Date): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/**
 * The earliest recording time a range admits, or undefined for "all".
 *
 * "7 days" means the last seven *days* including today, not 168 hours — a
 * recording from last Tuesday morning should not drop out of a week filter
 * because it is now Tuesday afternoon.
 */
export function rangeStart(range: DateRange, now: Date): Date | undefined {
  if (range === "all") return undefined;
  const midnight = startOfLocalDay(now);
  if (range === "today") return midnight;
  const days = range === "week" ? 6 : 29;
  return new Date(midnight.getTime() - days * 24 * 60 * 60 * 1000);
}

/**
 * Apply the view. Order is by when the recording was *made*, not when it
 * reached the phone — a capture restored from the server months later belongs
 * beside the ones it was recorded with.
 */
export function applyView(
  captures: readonly CaptureRecord[],
  view: CaptureView,
  now: Date = new Date(),
): CaptureRecord[] {
  const from = rangeStart(view.range, now);
  const filtered = captures.filter((capture) => {
    if (view.keptOnly && !capture.keep) return false;
    if (!from) return true;
    const recorded = new Date(capture.recordedAt);
    // An unparseable timestamp is kept rather than silently dropped: losing a
    // recording to a bad date field is worse than showing one out of range.
    if (Number.isNaN(recorded.getTime())) return true;
    return recorded >= from;
  });

  return filtered.sort((a, b) => {
    const left = new Date(a.recordedAt).getTime();
    const right = new Date(b.recordedAt).getTime();
    return view.order === "newest" ? right - left : left - right;
  });
}

/** Whether the view is hiding anything, for the "showing N of M" banner. */
export function isNarrowed(view: CaptureView): boolean {
  return view.keptOnly || view.unlabelledOnly || view.range !== "all";
}

/** One line describing what is being hidden, or undefined when nothing is. */
export function describeView(
  view: CaptureView,
  shown: number,
  total: number,
): string | undefined {
  if (!isNarrowed(view)) return undefined;
  const parts: string[] = [];
  if (view.range !== "all") parts.push(RANGE_LABELS[view.range].toLowerCase());
  if (view.keptOnly) parts.push("kept");
  // Named like the others, because a list narrowed to four rows with nothing
  // saying why is the thing this banner exists to prevent — it was once
  // reported as every capture disappearing.
  if (view.unlabelledOnly) parts.push("waiting to be labelled");
  return `Showing ${shown} of ${total} — ${parts.join(", ")}`;
}
