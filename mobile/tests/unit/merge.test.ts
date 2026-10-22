import { describe, expect, it } from "vitest";

import {
  MERGE_GAP_SEC,
  MergeRefused,
  planMerge,
  rebase,
  type MergePart,
} from "../../src/domain/merge";

const part = (uuid: string, recordedAt: string, durationMs: number,
              over: Partial<MergePart> = {}): MergePart => ({
  uuid,
  recordedAt,
  durationMs,
  sampleRate: 48000,
  channels: 1,
  audioPath: `/audio/${uuid}.wav`,
  ...over,
});

// The session that motivated the feature: captures 94-97, four recordings of
// one scene over ninety seconds.
const SESSION = [
  part("a", "2026-07-28T16:19:57Z", 19_000),
  part("b", "2026-07-28T16:20:50Z", 23_500),
  part("c", "2026-07-28T16:21:14Z", 14_500),
  part("d", "2026-07-28T16:21:47Z", 18_500),
];

describe("ordering", () => {
  it("orders by when it was recorded, not how it was selected", () => {
    const plan = planMerge([SESSION[2], SESSION[0], SESSION[3], SESSION[1]]);
    expect(plan.parts.map((p) => p.uuid)).toEqual(["a", "b", "c", "d"]);
  });

  it("takes its metadata from the earliest part", () => {
    const plan = planMerge([SESSION[3], SESSION[1]]);
    expect(plan.source.uuid).toBe("b");
  });

  it("is deterministic when two were recorded in the same instant", () => {
    const together = [part("z", "2026-07-28T16:19:57Z", 1000),
                      part("y", "2026-07-28T16:19:57Z", 1000)];
    expect(planMerge(together).parts.map((p) => p.uuid)).toEqual(["y", "z"]);
    expect(planMerge([...together].reverse()).parts.map((p) => p.uuid)).toEqual(["y", "z"]);
  });
});

describe("the timeline", () => {
  it("puts a gap between parts but not after the last one", () => {
    const plan = planMerge(SESSION);
    const gap = MERGE_GAP_SEC * 1000;
    expect(plan.parts.map((p) => p.offsetMs)).toEqual([
      0,
      19_000 + gap,
      19_000 + gap + 23_500 + gap,
      19_000 + gap + 23_500 + gap + 14_500 + gap,
    ]);
    expect(plan.totalMs).toBe(19_000 + 23_500 + 14_500 + 18_500 + gap * 3);
  });

  it("does not pad out the real twelve-minute gap between recordings", () => {
    const far = [part("a", "2026-07-28T10:31:00Z", 10_000),
                 part("b", "2026-07-28T10:44:00Z", 10_000)];
    expect(planMerge(far).totalMs).toBe(20_000 + MERGE_GAP_SEC * 1000);
  });

  it("allows a session with long pauses inside the hour", () => {
    const spread = [part("a", "2026-07-28T10:00:00Z", 10_000),
                    part("b", "2026-07-28T10:50:00Z", 10_000)];
    expect(planMerge(spread).parts).toHaveLength(2);
  });

  it("honours a caller-chosen gap", () => {
    expect(planMerge(SESSION.slice(0, 2), 0).totalMs).toBe(42_500);
  });
});

describe("refusing recordings that are not one event", () => {
  it("refuses parts more than an hour apart", () => {
    const apart = [part("morning", "2026-07-28T09:00:00Z", 10_000),
                   part("afternoon", "2026-07-28T14:00:00Z", 10_000)];
    expect(() => planMerge(apart)).toThrow(MergeRefused);
  });

  it("says how far apart, so the refusal is arguable", () => {
    const apart = [part("a", "2026-07-28T09:00:00Z", 10_000),
                   part("b", "2026-07-28T14:00:00Z", 10_000)];
    expect(() => planMerge(apart)).toThrow(/5\.0 hours apart/);
  });

  it("measures from the end of a part, not its start", () => {
    // A 50-minute recording followed 30 minutes later is 30 apart, not 80.
    const long = [part("long", "2026-07-28T09:00:00Z", 50 * 60_000),
                  part("next", "2026-07-28T10:20:00Z", 10_000)];
    expect(planMerge(long).parts).toHaveLength(2);
  });

  it("checks every consecutive pair, not just the ends", () => {
    const straddling = [part("a", "2026-07-28T09:00:00Z", 10_000),
                        part("b", "2026-07-28T12:00:00Z", 10_000),
                        part("c", "2026-07-28T12:00:20Z", 10_000)];
    expect(() => planMerge(straddling)).toThrow(/hours apart/);
  });
});

describe("refusing", () => {
  it("refuses a single capture", () => {
    expect(() => planMerge([SESSION[0]])).toThrow(MergeRefused);
  });

  it("refuses to resample", () => {
    const odd = part("x", "2026-07-28T16:30:00Z", 5000, { sampleRate: 44100 });
    expect(() => planMerge([SESSION[0], odd])).toThrow(/resampling/);
  });

  it("refuses to mix mono and stereo", () => {
    const stereo = part("x", "2026-07-28T16:30:00Z", 5000, { channels: 2 });
    expect(() => planMerge([SESSION[0], stereo])).toThrow(MergeRefused);
  });
});

describe("rebasing the offsets that carry human judgement", () => {
  it("leaves a label in the first part where it was", () => {
    const plan = planMerge(SESSION);
    expect(rebase(plan, "a", 4.2)).toBe(4.2);
  });

  it("moves a label in a later part onto the merged timeline", () => {
    const plan = planMerge(SESSION);
    // 2s into part c, which starts at 19 + 3 + 23.5 + 3 = 48.5s
    expect(rebase(plan, "c", 2)).toBeCloseTo(50.5, 6);
  });

  it("keeps a label inside its own part's span", () => {
    const plan = planMerge(SESSION);
    const c = plan.parts.find((p) => p.uuid === "c")!;
    const at = rebase(plan, "c", 14.4);
    expect(at).toBeGreaterThan(c.offsetMs / 1000);
    expect(at).toBeLessThanOrEqual((c.offsetMs + c.durationMs) / 1000);
  });

  it("refuses a part that is not in the merge", () => {
    expect(() => rebase(planMerge(SESSION), "nope", 1)).toThrow(MergeRefused);
  });
});
