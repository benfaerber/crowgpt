import { describe, expect, it } from "vitest";

import {
  describeDictationState,
  dictationLabel,
  isPushable,
  isPendingSync,
  type DictationRecord,
} from "../../src/domain/dictations";

function memo(patch: Partial<DictationRecord> = {}): DictationRecord {
  return {
    uuid: "d1",
    captureUuid: "c1",
    audioPath: "/tmp/dictation_1.wav",
    recordedAt: "2026-08-01T18:55:00Z",
    durationMs: 42_000,
    bytes: 1_344_044,
    sampleRate: 16_000,
    channels: 1,
    state: "ready",
    uploadedBytes: 0,
    ...patch,
  };
}

/**
 * The guard that matters is the one against sending a header.
 *
 * A process killed a moment after the microphone opened leaves a 44-byte WAV.
 * Uploading it would look like a successful sync of an empty note, and the
 * server would queue a transcription job to listen to silence.
 */
describe("what may be sent", () => {
  it("sends a finished memo", () => {
    expect(isPushable(memo())).toBe(true);
  });

  it("never sends one the app died during", () => {
    expect(isPushable(memo({ state: "recording", bytes: 44 }))).toBe(false);
    expect(isPushable(memo({ state: "interrupted" }))).toBe(false);
  });

  it("never sends a bare header", () => {
    expect(isPushable(memo({ bytes: 44 }))).toBe(false);
  });

  it("never sends a slipped thumb", () => {
    // Short for an honest reason rather than a crash, and still not worth a
    // transcription job or the row it would appear as afterwards.
    expect(isPushable(memo({ durationMs: 300 }))).toBe(false);
  });

  it("stops once the server has all of it", () => {
    const sent = memo({ serverId: 7, uploadedBytes: 1_344_044 });
    expect(isPendingSync(sent)).toBe(false);
    expect(isPushable(sent)).toBe(false);
  });

  it("resumes one the server has only part of", () => {
    expect(isPushable(memo({ serverId: 7, uploadedBytes: 400_000 }))).toBe(true);
  });
});

describe("what it is called", () => {
  it("numbers them and states the length", () => {
    // An ordinal, never an invented title: nobody names a voice memo in a field.
    expect(dictationLabel(memo({ durationMs: 18_000 }), 1)).toBe("Note 2 · 0:18");
  });

  it("carries minutes when there are any", () => {
    expect(dictationLabel(memo({ durationMs: 95_000 }), 0)).toBe("Note 1 · 1:35");
  });
});

/**
 * Sync here is manual and push-only, so a note sitting on the phone is the
 * normal state. Saying nothing about it is how somebody assumes it is safe.
 */
describe("what it says about itself", () => {
  it("says it has not left the phone", () => {
    expect(describeDictationState(memo())).toBe("waiting to send");
  });

  it("shows progress while it is going up", () => {
    expect(describeDictationState(memo({ serverId: 7, uploadedBytes: 672_022 })))
      .toBe("sending — 50%");
  });

  it("never rounds an unfinished upload to 100%", () => {
    // Otherwise the last chunk reads as delivered before it is.
    expect(describeDictationState(memo({ serverId: 7, uploadedBytes: 1_344_000 })))
      .toBe("sending — 99%");
  });

  it("distinguishes sent from transcribed", () => {
    const sent = memo({ serverId: 7, uploadedBytes: 1_344_044,
                        syncedAt: "2026-08-01T19:00:00Z" });
    expect(describeDictationState(sent))
      .toBe("sent — transcript arrives on the next sync");
    expect(describeDictationState({ ...sent, transcript: "two of them were mobbing" }))
      .toBe("transcribed");
  });

  it("says out loud when the app died holding the pen", () => {
    // A silently missing memo is indistinguishable from one he forgot to make.
    expect(describeDictationState(memo({ state: "interrupted" })))
      .toBe("the app stopped while recording this");
  });
});
