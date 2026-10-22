import { beforeEach, describe, expect, it } from "vitest";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MergeFailed, mergeCaptures, unmergeCapture } from "../../src/domain/mergeCaptures";
import type { NewCapture } from "../../src/domain/types";

const capture = (uuid: string, recordedAt: string, over: Partial<NewCapture> = {}): NewCapture => ({
  uuid,
  mediaUuid: `${uuid}-media`,
  recordedAt,
  durationMs: 19_000,
  sampleRate: 48000,
  channels: 1,
  audioPath: `/audio/${uuid}.wav`,
  bytes: 1_824_044,
  ...over,
});

const IDS = { captureUuid: "m-1", mediaUuid: "m-1-media" };

describe("merging", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    // The earliest part carries the description of the event, as 94 would.
    await repo.add(capture("p1", "2026-07-28T16:20:50Z", { durationMs: 23_500 }));
    await repo.add(capture("p0", "2026-07-28T16:19:57Z", {
      name: "Peanut drop, family of five, mowers",
      notes: "four on the ground, one on a wire",
      keep: true,
      latitude: 40.7681,
      longitude: -111.88,
      adultCount: 2,
      juvenileCount: 2,
      unagedCount: 1,
    }));
  });

  it("leaves one capture in the list", async () => {
    await mergeCaptures(repo, ["p0", "p1"], IDS);
    expect((await repo.list()).map((c) => c.uuid)).toEqual(["m-1"]);
  });

  it("takes the whole description from the earliest part", async () => {
    const { merged } = await mergeCaptures(repo, ["p1", "p0"], IDS);
    expect(merged.name).toBe("Peanut drop, family of five, mowers");
    expect(merged.adultCount).toBe(2);
    expect(merged.juvenileCount).toBe(2);
    expect(merged.keep).toBe(true);
    expect(merged.latitude).toBeCloseTo(40.7681, 4);
  });

  it("begins when the first recording began", async () => {
    const { merged } = await mergeCaptures(repo, ["p1", "p0"], IDS);
    expect(merged.recordedAt).toBe("2026-07-28T16:19:57Z");
  });

  it("is as long as the parts plus the gap", async () => {
    const { merged } = await mergeCaptures(repo, ["p0", "p1"], IDS, 3);
    expect(merged.durationMs).toBe(19_000 + 3_000 + 23_500);
  });

  it("remembers its parts in play order, not selection order", async () => {
    const { merged } = await mergeCaptures(repo, ["p1", "p0"], IDS);
    expect(merged.mergedFrom).toEqual(["p0", "p1"]);
  });

  it("has never been synced, whatever its parts had done", async () => {
    await repo.update("p0", { serverCaptureId: 94, syncState: "synced" });
    const { merged } = await mergeCaptures(repo, ["p0", "p1"], IDS);
    expect(merged.syncState).toBe("local");
    expect(merged.serverCaptureId).toBeUndefined();
  });

  it("answers to a path no file source can satisfy", async () => {
    // Deliberate: its audio is assembled, so a plain read must fail loudly
    // rather than quietly returning the wrong bytes.
    const { merged } = await mergeCaptures(repo, ["p0", "p1"], IDS);
    expect(merged.audioPath).toBe("merged:m-1");
  });
});

describe("what the server needs told", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    await repo.add(capture("p0", "2026-07-28T16:19:57Z"));
    await repo.add(capture("p1", "2026-07-28T16:20:50Z"));
    await repo.add(capture("p2", "2026-07-28T16:21:14Z"));
  });

  it("lists only the parts that had reached it", async () => {
    await repo.update("p1", { serverCaptureId: 95, syncState: "synced" });
    const { syncedParts } = await mergeCaptures(repo, ["p0", "p1", "p2"], IDS);
    expect(syncedParts.map((p) => p.serverCaptureId)).toEqual([95]);
  });

  it("is empty when nothing had synced, so there is nothing to tell", async () => {
    const { syncedParts } = await mergeCaptures(repo, ["p0", "p1", "p2"], IDS);
    expect(syncedParts).toEqual([]);
  });
});

describe("refusing", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    await repo.add(capture("p0", "2026-07-28T16:19:57Z"));
    await repo.add(capture("p1", "2026-07-28T16:20:50Z"));
  });

  it("refuses a capture that is not there", async () => {
    await expect(mergeCaptures(repo, ["p0", "ghost"], IDS)).rejects.toThrow(MergeFailed);
  });

  it("refuses a part already folded into something else", async () => {
    await repo.update("p0", { mergedInto: "somewhere" });
    await expect(mergeCaptures(repo, ["p0", "p1"], IDS)).rejects.toThrow(/already part/);
  });

  it("refuses to nest one merge inside another", async () => {
    await repo.update("p0", { mergedFrom: ["a", "b"] });
    await expect(mergeCaptures(repo, ["p0", "p1"], IDS)).rejects.toThrow(/un-merge it first/);
  });

  it("refuses mismatched formats, through planMerge", async () => {
    await repo.add(capture("odd", "2026-07-28T16:30:00Z", { sampleRate: 44100 }));
    await expect(mergeCaptures(repo, ["p0", "odd"], IDS)).rejects.toThrow(/resampling/);
  });

  it("leaves every recording listed when it refuses", async () => {
    await repo.add(capture("odd", "2026-07-28T16:30:00Z", { channels: 2 }));
    await expect(mergeCaptures(repo, ["p0", "odd"], IDS)).rejects.toThrow();
    expect((await repo.list()).map((c) => c.uuid).sort()).toEqual(["odd", "p0", "p1"]);
  });
});

describe("un-merging", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    await repo.add(capture("p0", "2026-07-28T16:19:57Z"));
    await repo.add(capture("p1", "2026-07-28T16:20:50Z"));
    await mergeCaptures(repo, ["p0", "p1"], IDS);
  });

  it("puts the recordings back in the list", async () => {
    await unmergeCapture(repo, "m-1");
    expect((await repo.list()).map((c) => c.uuid).sort()).toEqual(["p0", "p1"]);
  });

  it("takes the merged capture away", async () => {
    await unmergeCapture(repo, "m-1");
    expect(await repo.get("m-1")).toBeNull();
  });

  it("returns the recordings it restored", async () => {
    expect((await unmergeCapture(repo, "m-1")).map((c) => c.uuid)).toEqual(["p0", "p1"]);
  });

  it("refuses a capture that is not a merge", async () => {
    await expect(unmergeCapture(repo, "p0")).rejects.toThrow(/not a merge/);
  });

  it("can be merged again afterwards", async () => {
    await unmergeCapture(repo, "m-1");
    const { merged } = await mergeCaptures(repo, ["p0", "p1"],
                                           { captureUuid: "m-2", mediaUuid: "m-2-media" });
    expect(merged.mergedFrom).toEqual(["p0", "p1"]);
  });
});
