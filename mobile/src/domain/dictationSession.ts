/**
 * What recording a spoken note costs the rolling buffer, decided before the tap.
 *
 * The recorder holds exactly one microphone session. `SessionState.beginRecording`
 * returns true when a listening session is already open, and `WavRecorder.start`
 * then drains the pre-roll ring into the new file — so starting a dictation over
 * a live buffer would put fifteen seconds of bird audio at the head of the memo
 * *and* empty the ring the whole feature exists to keep. `awaitPreviousThread`
 * refuses a second AudioRecord outright, calling two in one process "a coin
 * toss".
 *
 * So a dictation must close the buffer, record, and reopen it. Losing the ring
 * is not avoidable and is the same trade `adoptNewMicrophone` already accepts
 * for a microphone plugged in mid-session. What IS avoidable is the recordist
 * not knowing: the cost is knowable in seconds before the tap, so it is said.
 *
 * Pure, because both answers are rules — the same reason `micState` is.
 */

export interface DictationPlan {
  /** The buffer is open and this will close it. */
  closeListening: boolean;
  /** How much held past is about to be dropped, in ms. Zero if none. */
  ringLossMs: number;
}

export type DictationRefusal = { ok: false; reason: string };
export type DictationDecision = ({ ok: true } & DictationPlan) | DictationRefusal;

/**
 * Whether a dictation may start now, and what it costs.
 *
 * Refuses during a capture rather than interrupting one. A recording in
 * progress is the one thing in this app that cannot be recovered, and taking
 * the microphone off it to write a note about it would be the feature eating
 * its own subject.
 */
export function planDictation({
  listening,
  recording,
  bufferedMs,
}: {
  listening: boolean;
  recording: boolean;
  bufferedMs: number;
}): DictationDecision {
  if (recording) {
    return {
      ok: false,
      reason: "Stop the recording first — a note cannot share the microphone.",
    };
  }
  return {
    ok: true,
    closeListening: listening,
    ringLossMs: listening ? bufferedMs : 0,
  };
}

/**
 * Whether the buffer is owed a reopen once the note is finished.
 *
 * Two facts, not one: that this dictation closed it, and that the setting still
 * wants it open. The setting can be switched off *during* a note, and reopening
 * a microphone somebody has just turned off would be the app overruling them.
 */
export function shouldReopenListening({
  wasListening,
  preRollEnabled,
}: {
  wasListening: boolean;
  preRollEnabled: boolean;
}): boolean {
  return wasListening && preRollEnabled;
}

/**
 * What to warn before the tap, or nothing when there is no cost.
 *
 * Stated in seconds rather than as "the buffer will be cleared", because the
 * number is the part that decides whether to wait: fifteen seconds of held past
 * is worth protecting if the birds are active right now, and worth nothing at
 * all if they are not.
 */
export function describeRingCost(ringLossMs: number): string | undefined {
  const seconds = Math.floor(ringLossMs / 1000);
  if (seconds < 1) return undefined;
  return `This closes the rolling buffer — the ${seconds}s it is holding now `
    + "will be dropped, and it refills from empty afterwards.";
}
