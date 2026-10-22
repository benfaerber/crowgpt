import type { LabelRecord } from "./labels";

/** One thing to decide about: a detection, or a span marked by ear. */
export interface LabelCard {
  key: string;
  startSec: number;
  endSec: number;
  /** The model's guess, when there is one. */
  predicted?: string;
  /**
   * Other call types the head also heard in this span.
   *
   * Carried onto the card because it changes what the recordist is being
   * asked. A span the analyzer heard two things in is not a "which one is it"
   * question — it is an invitation to mark the second call by ear, which is
   * the only way a concurrent call has ever reached this corpus.
   */
  alternates?: { call_type: string; confidence: number }[];
  /** Whether the alternates are independent scores or a softmax runner-up. */
  multiLabel?: boolean;
  /** The decision already made, if any. */
  label?: LabelRecord;
  /**
   * The model named a corvid but was not confident.
   *
   * Shown differently rather than hidden: these are the faint and awkward calls
   * the model is worst at, so they are the ones the training set most needs —
   * and they can only get there by being offered. "Not a crow" is just as
   * useful an answer, and it is a negative example nothing else produces.
   */
  candidate?: boolean;
}

/** A detection as the analyzer reports it. */
export interface DetectedSpan {
  start_sec: number;
  end_sec: number;
  call_type?: string | null;
  /** 1 when the analyzer was unsure. See LabelCard.candidate. */
  candidate?: number | null;
  /** Other call types heard in the same span. See LabelCard.alternates. */
  alternates?: { call_type: string; confidence: number }[];
  multi_label?: boolean;
}

/** Spans within this of each other are the same call. */
const SAME_SPAN_SEC = 0.01;

/**
 * The deck: every detection, plus every span marked by ear, in time order.
 *
 * Each label is claimed by at most one card. Without that, two detections
 * covering the same span both match the same label, the deck counts it twice,
 * and its "decided" total disagrees with the number of labels that exist — which
 * is exactly how the capture screen and the deck came to report 9 and 10 for the
 * same recording.
 *
 * Claiming also means every label lands on exactly one card, so "cards decided"
 * and "labels recorded" are the same number by construction rather than by two
 * pieces of code agreeing to count the same way.
 */
export function buildLabelCards(
  detections: DetectedSpan[],
  labels: LabelRecord[],
): LabelCard[] {
  const unclaimed = new Set(labels.map((label) => label.uuid));

  const fromDetections = detections.map((detection, index): LabelCard => {
    const match = labels.find(
      (label) =>
        unclaimed.has(label.uuid) &&
        Math.abs(label.startSec - detection.start_sec) < SAME_SPAN_SEC &&
        Math.abs(label.endSec - detection.end_sec) < SAME_SPAN_SEC,
    );
    if (match) unclaimed.delete(match.uuid);
    return {
      key: `det-${index}-${detection.start_sec}`,
      startSec: detection.start_sec,
      endSec: detection.end_sec,
      predicted: detection.call_type ?? undefined,
      alternates: detection.alternates?.length ? detection.alternates : undefined,
      multiLabel: detection.multi_label,
      candidate: Boolean(detection.candidate),
      label: match,
    };
  });

  const byEar = labels
    .filter((label) => unclaimed.has(label.uuid))
    .map((label): LabelCard => ({
      key: `ear-${label.uuid}`,
      startSec: label.startSec,
      endSec: label.endSec,
      label,
    }));

  return [...fromDetections, ...byEar].sort((a, b) => a.startSec - b.startSec);
}

/** How many cards carry a decision. Equal to the number of labels, by construction. */
export function countDecided(cards: LabelCard[]): number {
  return cards.filter((card) => card.label !== undefined).length;
}
