import { describe, expect, it } from "vitest";

import {
  describeRingCost,
  planDictation,
  shouldReopenListening,
} from "../../src/domain/dictationSession";

/**
 * The recorder holds one microphone session, and starting a dictation over an
 * open rolling buffer would drain the pre-roll ring into the memo — fifteen
 * seconds of bird audio at the head of a voice note, and the ring gone. So a
 * dictation closes the buffer first, and the cost of that is knowable in
 * seconds before the tap.
 */
describe("whether a note may start", () => {
  it("refuses while a capture is running", () => {
    // The one thing in this app that cannot be recovered. Taking the microphone
    // off a recording to write a note about it would be the feature eating its
    // own subject.
    const decision = planDictation({ listening: true, recording: true, bufferedMs: 9000 });
    expect(decision.ok).toBe(false);
    if (!decision.ok) expect(decision.reason).toContain("Stop the recording first");
  });

  it("closes the buffer and says what that costs", () => {
    const decision = planDictation({ listening: true, recording: false, bufferedMs: 12_000 });
    expect(decision).toEqual({ ok: true, closeListening: true, ringLossMs: 12_000 });
  });

  it("costs nothing when the buffer is not open", () => {
    const decision = planDictation({ listening: false, recording: false, bufferedMs: 0 });
    expect(decision).toEqual({ ok: true, closeListening: false, ringLossMs: 0 });
  });
});

describe("whether the buffer is owed a reopen", () => {
  it("reopens what this note closed", () => {
    expect(shouldReopenListening({ wasListening: true, preRollEnabled: true })).toBe(true);
  });

  it("does not open one that was never open", () => {
    expect(shouldReopenListening({ wasListening: false, preRollEnabled: true })).toBe(false);
  });

  it("respects the setting being turned off mid-note", () => {
    // Reopening a microphone somebody has just switched off would be the app
    // overruling them about their own phone.
    expect(shouldReopenListening({ wasListening: true, preRollEnabled: false })).toBe(false);
  });
});

describe("what the recordist is told before tapping", () => {
  it("names the seconds, because the number is the decision", () => {
    // Fifteen seconds of held past is worth protecting if the birds are active
    // right now, and worth nothing at all if they are not.
    expect(describeRingCost(15_000)).toContain("the 15s it is holding now");
  });

  it("says nothing when there is nothing to lose", () => {
    expect(describeRingCost(0)).toBeUndefined();
    expect(describeRingCost(400)).toBeUndefined();
  });
});
