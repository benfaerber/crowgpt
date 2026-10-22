import { describe, expect, it } from "vitest";

import {
  daysSinceRecorded,
  labelFreshness,
  labelQueue,
  labelState,
  needsLabelling,
} from "../../src/domain/labelQueue";
import type { CaptureRecord } from "../../src/domain/types";

function capture(patch: Partial<CaptureRecord> & { uuid: string }): CaptureRecord {
  return {
    mediaUuid: `m-${patch.uuid}`,
    recordedAt: "2026-08-01T09:00:00Z",
    durationMs: 3000,
    sampleRate: 48000,
    channels: 1,
    audioPath: `/tmp/${patch.uuid}.wav`,
    bytes: 1000,
    syncState: "local",
    uploadedBytes: 0,
    attempts: 0,
    keep: true,
    localRevision: 0,
    syncedRevision: 0,
    ...patch,
  };
}

/**
 * The queue is only as good as its ability to become empty.
 *
 * One that lists recordings nobody will ever label gets ignored within a week,
 * and then it is worse than no queue — it has trained the one person who uses
 * it to look past it. So most of what matters here is what stays OUT.
 */
describe("what needs labelling", () => {
  it("wants a kept recording nobody has labelled", () => {
    expect(needsLabelling(capture({ uuid: "a" }), 0)).toBe(true);
  });

  it("drops one as soon as it has a label", () => {
    expect(needsLabelling(capture({ uuid: "a" }), 1)).toBe(false);
  });

  it("ignores anything not marked ★ Keep", () => {
    // The corpus is mostly seeded archive clips and test uploads. Without
    // this the queue opens onto a hundred recordings nobody intends to label.
    expect(needsLabelling(capture({ uuid: "a", keep: false }), 0)).toBe(false);
  });

  it("ignores a capture that was merged into another", () => {
    // The merge is the recording now; labelling both would enter the same call
    // into the corpus twice.
    expect(needsLabelling(capture({ uuid: "a", mergedInto: "b" }), 0)).toBe(false);
  });

  it("drops one waved past as having nothing to label", () => {
    expect(
      needsLabelling(capture({ uuid: "a", nothingToLabelAt: "2026-08-01T10:00:00Z" }), 0),
    ).toBe(false);
  });
});

describe("what state a capture is in", () => {
  it("separates labelled from dismissed from waiting", () => {
    // Three states, not two: "somebody labelled it" and "somebody said there
    // was nothing here" are different facts and only one is about crows.
    expect(labelState(capture({ uuid: "a" }), 2)).toBe("labelled");
    expect(labelState(capture({ uuid: "b", nothingToLabelAt: "x" }), 0))
      .toBe("nothing-to-label");
    expect(labelState(capture({ uuid: "c" }), 0)).toBe("waiting");
  });

  it("lets a label override an earlier dismissal", () => {
    // Labelling something you had waved past is a correction, not an error —
    // the label is evidence and the dismissal was only an intention.
    expect(labelState(capture({ uuid: "a", nothingToLabelAt: "x" }), 1)).toBe("labelled");
  });
});

describe("the queue itself", () => {
  it("puts the newest recording first", () => {
    // The whole point. What makes a label good is how recently the recordist
    // watched it happen, so if only one gets done today it should be that one.
    const queue = labelQueue(
      [
        capture({ uuid: "old", recordedAt: "2026-07-28T09:00:00Z" }),
        capture({ uuid: "new", recordedAt: "2026-08-01T18:55:00Z" }),
        capture({ uuid: "mid", recordedAt: "2026-07-30T09:00:00Z" }),
      ],
      new Map(),
    );
    expect(queue.map((c) => c.uuid)).toEqual(["new", "mid", "old"]);
  });

  it("reads a missing count as none", () => {
    // countsByCapture omits captures with no labels rather than storing zeroes.
    expect(labelQueue([capture({ uuid: "a" })], new Map()).map((c) => c.uuid))
      .toEqual(["a"]);
  });

  it("leaves out everything already dealt with", () => {
    const queue = labelQueue(
      [
        capture({ uuid: "labelled" }),
        capture({ uuid: "dismissed", nothingToLabelAt: "x" }),
        capture({ uuid: "seeded", keep: false }),
        capture({ uuid: "waiting" }),
      ],
      new Map([["labelled", 3]]),
    );
    expect(queue.map((c) => c.uuid)).toEqual(["waiting"]);
  });
});

/**
 * Today's queue and last week's forgotten call are not the same job.
 *
 * Both are unlabelled. One is remembering what you watched happen; the other is
 * listening to a file and inferring, which is a weaker claim — and the corpus
 * cannot tell the two apart afterwards, so the screen has to.
 */
describe("how cold a recording has gone", () => {
  const now = new Date(2026, 7, 8, 14, 0); // 8 Aug 2026, local
  const at = (y: number, m: number, d: number, h = 9) =>
    capture({ uuid: `${y}-${m}-${d}`, recordedAt: new Date(y, m, d, h).toISOString() });

  it("counts nights, not 24-hour blocks", () => {
    // 11pm yesterday to 2pm today is 15 hours and one night, and a person
    // reaching for it says "last night" — so it is a day old, not zero.
    expect(daysSinceRecorded(at(2026, 7, 7, 23), now)).toBe(1);
    expect(daysSinceRecorded(at(2026, 7, 8, 9), now)).toBe(0);
  });

  it("keeps three days fresh and turns on the fourth", () => {
    // The boundary is the whole feature: at MEMORY_DAYS it is still fresh.
    expect(labelFreshness(at(2026, 7, 8), now)).toBe("fresh");
    expect(labelFreshness(at(2026, 7, 5), now)).toBe("fresh");
    expect(labelFreshness(at(2026, 7, 4), now)).toBe("cold");
  });

  it("calls last week's recording cold", () => {
    expect(labelFreshness(at(2026, 7, 1), now)).toBe("cold");
  });

  it("never reports a negative age for a clock that is ahead", () => {
    // A phone whose clock is a few minutes fast would otherwise render "-0d".
    expect(daysSinceRecorded(at(2026, 7, 9), now)).toBe(0);
  });

  it("leaves a cold recording in the queue", () => {
    // Not a deadline. What has decayed is how good the label can be, not
    // whether it is worth making — dropping it would silently shrink the
    // corpus for the crime of being old.
    expect(needsLabelling(at(2026, 6, 20), 0)).toBe(true);
  });
});
