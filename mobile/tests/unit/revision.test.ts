import { describe, expect, it } from "vitest";

import { isDirtyingChange, hasUnsyncedEdits } from "../../src/domain/revision";
import { isPendingSync, type CaptureRecord } from "../../src/domain/types";
import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";

function capture(overrides: Partial<CaptureRecord> = {}): CaptureRecord {
  return {
    uuid: "cap-1",
    mediaUuid: "med-1",
    recordedAt: "2026-07-25T18:00:00Z",
    durationMs: 5000,
    sampleRate: 48000,
    channels: 1,
    audioPath: "/tmp/cap-1.wav",
    bytes: 1000,
    syncState: "synced",
    uploadedBytes: 1000,
    attempts: 1,
    localRevision: 0,
    syncedRevision: 0,
    ...overrides,
  };
}

describe("isDirtyingChange", () => {
  it("notices an edited description", () => {
    expect(isDirtyingChange(capture({ description: "one" }), { description: "two" })).toBe(true);
  });

  it("notices a description added after the upload", () => {
    // The case that started this: a note typed once the capture was already
    // synced had no way to reach the server.
    expect(isDirtyingChange(capture(), { description: "Edgar alone, calling." })).toBe(true);
  });

  it.each([
    ["keep", { keep: true }],
    ["family", { familyUuid: "fam-2" }],
    ["notes", { notes: "by the feeder" }],
    ["location name", { locationName: "Liberty Park" }],
  ])("notices a changed %s", (_label, patch) => {
    expect(isDirtyingChange(capture(), patch)).toBe(true);
  });

  it("ignores a write that changes nothing", () => {
    // Screens routinely save a field they didn't touch; a re-sync per keystroke
    // of an unchanged form would be its own bug.
    expect(isDirtyingChange(capture({ description: "same" }), { description: "same" })).toBe(false);
  });

  it.each([
    ["server capture id", { serverCaptureId: 12 }],
    ["uploaded bytes", { uploadedBytes: 512 }],
    ["sync state", { syncState: "syncing" as const }],
    ["attempts", { attempts: 3 }],
    ["synced at", { syncedAt: "2026-07-25T19:00:00Z" }],
    ["last error", { lastError: "timeout" }],
  ])("ignores sync bookkeeping: %s", (_label, patch) => {
    // If the sync dirtied the record it was cleaning, it would never settle.
    expect(isDirtyingChange(capture(), patch)).toBe(false);
  });

  it("treats undefined, null and empty string as the same absence", () => {
    // These round-trip differently through SQLite; a spurious difference here
    // would queue every capture for a pointless re-push.
    expect(isDirtyingChange(capture({ notes: undefined }), { notes: "" })).toBe(false);
  });

  it("does not dirty on a crop change", () => {
    // Re-cropping after the audio landed needs the corrected bytes re-uploaded
    // under a fresh media id — a different feature, deliberately not this one.
    expect(isDirtyingChange(capture(), { cropStartSec: 2 })).toBe(false);
  });
});

describe("isPendingSync", () => {
  it("selects a capture edited since it synced", () => {
    expect(isPendingSync(capture({ localRevision: 2, syncedRevision: 1 }))).toBe(true);
  });

  it("leaves a fully-synced capture alone", () => {
    expect(isPendingSync(capture({ localRevision: 1, syncedRevision: 1 }))).toBe(false);
  });

  it("still selects never-sent and failed captures", () => {
    expect(isPendingSync(capture({ syncState: "local" }))).toBe(true);
    expect(isPendingSync(capture({ syncState: "failed" }))).toBe(true);
  });

  it("never selects one that is already in flight", () => {
    // Picking it up again mid-upload would run two syncs over the same file.
    expect(isPendingSync(capture({ syncState: "syncing", localRevision: 9 }))).toBe(false);
  });

  it("treats a capture with no revision columns as clean", () => {
    // Rows written before the migration; they must not all queue for re-push.
    const legacy = capture({ localRevision: undefined, syncedRevision: undefined });
    expect(hasUnsyncedEdits(legacy)).toBe(false);
    expect(isPendingSync(legacy)).toBe(false);
  });
});

describe("the repository bumps the revision", () => {
  async function synced() {
    const repository = new MemoryCaptureRepository();
    await repository.add(capture());
    await repository.update("cap-1", { syncState: "synced", syncedRevision: 0 });
    return repository;
  }

  it("makes an edited capture pending again", async () => {
    const repository = await synced();
    expect(await repository.pendingSync()).toHaveLength(0);

    await repository.update("cap-1", { description: "typed at the desk" });

    expect((await repository.pendingSync()).map((c) => c.uuid)).toEqual(["cap-1"]);
  });

  it("bumps once per distinct edit, not per write", async () => {
    const repository = await synced();
    await repository.update("cap-1", { description: "one" });
    await repository.update("cap-1", { description: "one" });
    const record = await repository.get("cap-1");
    expect(record?.localRevision).toBe(1);
  });

  it("leaves the capture clean once the sync records the revision", async () => {
    const repository = await synced();
    await repository.update("cap-1", { description: "typed at the desk" });
    const dirty = await repository.get("cap-1");

    await repository.update("cap-1", {
      syncState: "synced",
      syncedRevision: dirty!.localRevision,
    });

    expect(await repository.pendingSync()).toHaveLength(0);
  });

  it("keeps an edit made during a sync owed afterwards", async () => {
    const repository = await synced();
    const beforePush = (await repository.get("cap-1"))!.localRevision ?? 0;
    // The user types while the upload is in flight.
    await repository.update("cap-1", { description: "typed mid-upload" });
    // The sync finishes and records the revision it started with.
    await repository.update("cap-1", { syncState: "synced", syncedRevision: beforePush });

    expect(await repository.pendingSync()).toHaveLength(1);
  });
});
