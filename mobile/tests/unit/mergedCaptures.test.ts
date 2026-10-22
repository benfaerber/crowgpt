import { beforeEach, describe, expect, it } from "vitest";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import type { NewCapture } from "../../src/domain/types";

/**
 * What a merge does to the capture list, and what un-does it.
 *
 * Run against the in-memory repository because the SQLite one needs expo's
 * native module. The two implement one interface and the rules below are that
 * interface's, so mirroring them is not duplication — it is what keeps a
 * behaviour the UI depends on from being true in only one of them.
 */

const capture = (uuid: string, recordedAt: string): NewCapture => ({
  uuid,
  mediaUuid: `${uuid}-media`,
  recordedAt,
  durationMs: 19_000,
  sampleRate: 48000,
  channels: 1,
  audioPath: `/audio/${uuid}.wav`,
  bytes: 1_824_044,
});

describe("a merged capture and its parts", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    // The shape of captures 94-97: three parts, folded into a fourth row.
    for (const [uuid, at] of [["p0", "2026-07-28T16:19:57Z"],
                              ["p1", "2026-07-28T16:20:50Z"],
                              ["p2", "2026-07-28T16:21:14Z"]] as const) {
      await repo.add(capture(uuid, at));
    }
    await repo.add(capture("merged", "2026-07-28T16:19:57Z"));
    await repo.update("merged", { mergedFrom: ["p0", "p1", "p2"] });
    for (const uuid of ["p0", "p1", "p2"]) {
      await repo.update(uuid, { mergedInto: "merged" });
    }
  });

  it("shows the merge and not the parts", async () => {
    expect((await repo.list()).map((c) => c.uuid)).toEqual(["merged"]);
  });

  it("keeps every part fetchable by uuid", async () => {
    // Not listed is not deleted. This is the whole recovery story.
    for (const uuid of ["p0", "p1", "p2"]) {
      expect(await repo.get(uuid)).not.toBeNull();
    }
  });

  it("keeps each part's audio path, because the merge reads through to it", async () => {
    const part = await repo.get("p1");
    expect(part?.audioPath).toBe("/audio/p1.wav");
  });

  it("remembers the parts in play order", async () => {
    expect((await repo.get("merged"))?.mergedFrom).toEqual(["p0", "p1", "p2"]);
  });
});

describe("undoing", () => {
  let repo: MemoryCaptureRepository;

  beforeEach(async () => {
    repo = new MemoryCaptureRepository();
    await repo.add(capture("p0", "2026-07-28T16:19:57Z"));
    await repo.add(capture("p1", "2026-07-28T16:20:50Z"));
    await repo.add(capture("merged", "2026-07-28T16:19:57Z"));
    await repo.update("merged", { mergedFrom: ["p0", "p1"] });
    await repo.update("p0", { mergedInto: "merged" });
    await repo.update("p1", { mergedInto: "merged" });
  });

  it("clearing the field brings a part back to the list", async () => {
    await repo.update("p0", { mergedInto: undefined });
    expect((await repo.list()).map((c) => c.uuid).sort()).toEqual(["merged", "p0"]);
  });

  it("deleting the merge releases its parts rather than stranding them", async () => {
    // The bug this exists for: delete the merge and the parts keep pointing at
    // a row that is gone, so list() hides them forever and nothing is left to
    // clear the field from. Recordings on disk, invisible, unrecoverable.
    await repo.remove("merged");
    expect((await repo.list()).map((c) => c.uuid).sort()).toEqual(["p0", "p1"]);
  });

  it("deleting the merge does not delete the recordings", async () => {
    await repo.remove("merged");
    expect(await repo.get("p0")).not.toBeNull();
    expect(await repo.get("p1")).not.toBeNull();
  });

  it("deleting a plain capture still just deletes it", async () => {
    await repo.add(capture("solo", "2026-07-28T17:00:00Z"));
    await repo.remove("solo");
    expect(await repo.get("solo")).toBeNull();
    expect((await repo.list()).map((c) => c.uuid)).toEqual(["merged"]);
  });
});
