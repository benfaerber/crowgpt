import { describe, expect, it } from "vitest";

import {
  captureFromOrphan,
  worthRecovering,
  MIN_RECOVERABLE_MS,
  type OrphanAudio,
} from "../../src/domain/recoverCaptures";

const orphan = (over: Partial<OrphanAudio> = {}): OrphanAudio => ({
  path: "/data/user/0/com.cawtalker.field/cache/capture_1.wav",
  bytes: 1_920_044,
  durationMs: 20_000,
  sampleRate: 48000,
  // 2026-07-29T21:00:00Z
  modifiedAt: Date.UTC(2026, 6, 29, 21, 0, 0),
  ...over,
});

/**
 * Recovering a recording the app was killed during.
 *
 * Measured on the Pixel 8: force-stopping mid-recording lost the capture
 * completely — the samples were on disk and nothing pointed at them. What these
 * tests protect is not the mechanism but the honesty of the row it produces.
 */
describe("recovering abandoned audio", () => {
  it("keeps the audio that was actually captured", () => {
    const capture = captureFromOrphan(orphan(), { uuid: "u", mediaUuid: "m" });
    expect(capture.audioPath).toBe(orphan().path);
    expect(capture.bytes).toBe(1_920_044);
    expect(capture.durationMs).toBe(20_000);
    expect(capture.sampleRate).toBe(48000);
    expect(capture.channels).toBe(1);
  });

  it("dates the recording by counting back from the file", () => {
    // The row that would have said when it started was never written, so the
    // mtime minus the duration is the best available answer — the same
    // arithmetic a healthy stop does against the wall clock.
    const capture = captureFromOrphan(orphan(), { uuid: "u", mediaUuid: "m" });
    expect(capture.recordedAt).toBe("2026-07-29T20:59:40.000Z");
  });

  it("says on the capture that it was recovered and is missing its end", () => {
    // A recovered capture is not the same object as one somebody stopped, and a
    // list that showed them identically would be lying by omission.
    const capture = captureFromOrphan(orphan(), { uuid: "u", mediaUuid: "m" });
    expect(capture.notes).toMatch(/recovered/i);
    expect(capture.notes).toMatch(/never written|end/i);
  });

  it("invents no location, region or input device", () => {
    // Those were known only to the process that died. A guess here puts
    // fiction in the corpus next to measurements.
    const capture = captureFromOrphan(orphan(), { uuid: "u", mediaUuid: "m" });
    expect(capture.latitude).toBeUndefined();
    expect(capture.longitude).toBeUndefined();
    expect(capture.region).toBeUndefined();
    expect(capture.inputDevice).toBeUndefined();
    expect(capture.inputHonoured).toBeUndefined();
  });

  it("carries the ids it was given, so a re-run cannot duplicate a capture", () => {
    const capture = captureFromOrphan(orphan(), { uuid: "abc", mediaUuid: "def" });
    expect(capture.uuid).toBe("abc");
    expect(capture.mediaUuid).toBe("def");
  });

  it("ignores a fragment too short to be a call", () => {
    // Killed within a second of the button: a misfire, not a recording, and a
    // list filling with half-second rows is a list nobody reads.
    const found = worthRecovering([
      orphan({ path: "/cache/capture_short.wav", durationMs: 400 }),
      orphan({ path: "/cache/capture_real.wav", durationMs: 12_000 }),
    ]);
    expect(found.map((o) => o.path)).toEqual(["/cache/capture_real.wav"]);
  });

  it("keeps one exactly at the threshold", () => {
    expect(worthRecovering([orphan({ durationMs: MIN_RECOVERABLE_MS })])).toHaveLength(1);
  });

  it("recovers nothing when there is nothing to recover", () => {
    // The ordinary launch, which is every launch but one.
    expect(worthRecovering([])).toEqual([]);
  });
});
