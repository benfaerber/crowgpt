/**
 * The store contract, held against BOTH implementations.
 *
 * Every other test runs against the Memory* fakes, which proves the app logic
 * and nothing about the phone: the Sqlite* repositories had no tests at all,
 * and the one recorded data loss in this app came from exactly that gap — the
 * SQLite INSERT drifted from `update` and a filmed capture silently lost its
 * video the instant it was saved.
 *
 * So each contract below runs twice, once per implementation, via a real
 * SQLite on the host (tests/support/expoSqliteShim.ts). A behaviour the two
 * disagree on fails here by name instead of shipping as a difference between
 * the test suite's world and the phone's.
 */

import { describe, expect, it } from "vitest";

import { MemoryAnalysisCache } from "../../src/data/MemoryAnalysisCache";
import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryFamilyRepository } from "../../src/data/MemoryFamilyRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { MemoryLogRepository } from "../../src/data/MemoryLogRepository";
import { MemoryDictationRepository } from "../../src/data/MemoryDictationRepository";
import { MemorySightingRepository } from "../../src/data/MemorySightingRepository";
import { SqliteAnalysisCache } from "../../src/data/SqliteAnalysisCache";
import { SqliteCaptureRepository } from "../../src/data/SqliteCaptureRepository";
import { SqliteContextRepository } from "../../src/data/SqliteContextRepository";
import { SqliteFamilyRepository } from "../../src/data/SqliteFamilyRepository";
import { SqliteLabelRepository } from "../../src/data/SqliteLabelRepository";
import { SqliteLogRepository } from "../../src/data/SqliteLogRepository";
import { SqliteDictationRepository } from "../../src/data/SqliteDictationRepository";
import { SqliteSightingRepository } from "../../src/data/SqliteSightingRepository";
import { CaptureNotFound } from "../../src/data/CaptureRepository";
import type { NewCapture } from "../../src/domain/types";

/** Each opened name is its own in-memory database — one per test. */
let dbCounter = 0;
const freshName = () => `contract-${dbCounter++}.db`;

function capture(uuid: string, over: Partial<NewCapture> = {}): NewCapture {
  return {
    uuid,
    mediaUuid: `${uuid}-media`,
    recordedAt: "2026-07-30T10:00:00Z",
    durationMs: 10_000,
    sampleRate: 48000,
    channels: 1,
    audioPath: `/data/${uuid}.wav`,
    bytes: 960_000,
    keep: false,
    localRevision: 0,
    syncedRevision: 0,
    ...over,
  };
}

describe.each([
  ["memory", async () => new MemoryCaptureRepository()],
  ["sqlite", () => SqliteCaptureRepository.open(freshName())],
])("CaptureRepository (%s)", (_kind, openRepo) => {
  it("round-trips every optional field through add", async () => {
    // The video-loss regression, held as a contract: a field accepted by add
    // must come back from get, on both implementations, or it was silently
    // dropped at the moment of saving.
    const repo = await openRepo();
    const full = capture("full", {
      name: "Edgar on the wire",
      videoPath: "/data/full.mp4",
      videoBytes: 5_000_000,
      videoMediaUuid: "full-video",
      videoUploadedBytes: 0,
      latitude: 40.76,
      longitude: -111.89,
      locationName: "the wire",
      region: "Salt Lake County, Utah",
      notes: "alone, calling",
      keep: true,
      familyUuid: undefined,
      cropStartSec: 1.5,
      cropEndSec: 8.25,
      inputDevice: "USB_HEADSET",
      inputHonoured: true,
      preRollSec: 12.5,
      appVersion: 344,
      appCommit: "abc123",
      observerRole: "known_feeder",
      distanceBand: "10_25m",
      adultCount: 2,
      juvenileCount: 1,
      unagedCount: 0,
      behaviorGuess: "contact",
    });
    await repo.add(full);
    const stored = await repo.get("full");
    expect(stored).not.toBeNull();
    for (const [field, wanted] of Object.entries(full)) {
      expect(stored![field as keyof NewCapture], field).toEqual(wanted);
    }
  });

  it("starts a fresh capture local, unsent and unattempted", async () => {
    const repo = await openRepo();
    const added = await repo.add(capture("fresh"));
    expect(added.syncState).toBe("local");
    expect(added.uploadedBytes).toBe(0);
    expect(added.attempts).toBe(0);
  });

  it("round-trips booleans and string lists through update", async () => {
    const repo = await openRepo();
    await repo.add(capture("flags"));
    const updated = await repo.update("flags", {
      keep: true,
      mergedFrom: ["part-1", "part-2"],
    });
    expect(updated.keep).toBe(true);
    expect(updated.mergedFrom).toEqual(["part-1", "part-2"]);
    expect((await repo.update("flags", { keep: false })).keep).toBe(false);
  });

  it("refuses to update a capture that does not exist", async () => {
    const repo = await openRepo();
    await expect(repo.update("ghost", { name: "x" })).rejects.toThrow(CaptureNotFound);
  });

  it("lists newest first and hides merged parts", async () => {
    const repo = await openRepo();
    await repo.add(capture("older", { recordedAt: "2026-07-30T09:00:00Z" }));
    await repo.add(capture("newer", { recordedAt: "2026-07-30T11:00:00Z" }));
    await repo.add(capture("part", { recordedAt: "2026-07-30T10:00:00Z" }));
    await repo.update("part", { mergedInto: "newer" });

    const listed = await repo.list();
    expect(listed.map((c) => c.uuid)).toEqual(["newer", "older"]);
  });

  it("still admits a part's audio path exists", async () => {
    // Orphan recovery asks "is any file on disk unaccounted for" — a hidden
    // part answered as unaccounted would be resurrected as a fresh capture.
    const repo = await openRepo();
    await repo.add(capture("whole"));
    await repo.add(capture("part"));
    await repo.update("part", { mergedInto: "whole" });
    expect(await repo.audioPaths()).toContain("/data/part.wav");
  });

  it("queues local and failed oldest first, leaves synced alone", async () => {
    const repo = await openRepo();
    await repo.add(capture("done", { recordedAt: "2026-07-30T08:00:00Z" }));
    await repo.update("done", { syncState: "synced" });
    await repo.add(capture("second", { recordedAt: "2026-07-30T10:00:00Z" }));
    await repo.add(capture("first", { recordedAt: "2026-07-30T09:00:00Z" }));
    await repo.update("first", { syncState: "failed" });

    const pending = await repo.pendingSync();
    expect(pending.map((c) => c.uuid)).toEqual(["first", "second"]);
  });

  it("re-queues a synced capture once an edit outruns the synced revision", async () => {
    // The post-sync description fix: without this a synced capture could
    // never owe the server anything again.
    const repo = await openRepo();
    await repo.add(capture("edited"));
    await repo.update("edited", { syncState: "synced", localRevision: 3, syncedRevision: 3 });
    await repo.update("edited", { localRevision: 4 });
    expect((await repo.pendingSync()).map((c) => c.uuid)).toEqual(["edited"]);
  });

  it("never queues a merged part on its own", async () => {
    const repo = await openRepo();
    await repo.add(capture("joined"));
    await repo.add(capture("folded"));
    await repo.update("folded", { mergedInto: "joined" });
    expect((await repo.pendingSync()).map((c) => c.uuid)).toEqual(["joined"]);
  });

  it("removing a merged capture un-hides its parts", async () => {
    const repo = await openRepo();
    await repo.add(capture("joined"));
    await repo.add(capture("folded"));
    await repo.update("folded", { mergedInto: "joined" });
    await repo.remove("joined");
    expect((await repo.list()).map((c) => c.uuid)).toEqual(["folded"]);
    expect((await repo.get("folded"))!.mergedInto).toBeUndefined();
  });

  it("forgetting server state rewinds every capture to local", async () => {
    const repo = await openRepo();
    await repo.add(capture("sent"));
    await repo.update("sent", {
      syncState: "synced", serverCaptureId: 7, serverMediaId: 9,
      uploadedBytes: 960_000, syncedAt: "2026-07-30T12:00:00Z", lastError: "old",
    });
    await repo.forgetServerState();
    const reset = await repo.get("sent");
    expect(reset!.syncState).toBe("local");
    expect(reset!.serverCaptureId).toBeUndefined();
    expect(reset!.serverMediaId).toBeUndefined();
    expect(reset!.uploadedBytes).toBe(0);
    expect(reset!.lastError).toBeUndefined();
  });

  it("recovers captures a dead sync left claiming to be in flight", async () => {
    const repo = await openRepo();
    await repo.add(capture("stuck"));
    await repo.update("stuck", { syncState: "syncing" });
    expect(await repo.recoverInterrupted()).toBe(1);
    const recovered = await repo.get("stuck");
    expect(recovered!.syncState).toBe("failed");
    expect(recovered!.lastError).toBeTruthy();
    expect((await repo.pendingSync()).map((c) => c.uuid)).toEqual(["stuck"]);
  });
});

describe.each([
  ["memory", async () => new MemoryFamilyRepository()],
  ["sqlite", () => SqliteFamilyRepository.open(freshName())],
])("FamilyRepository (%s)", (_kind, openRepo) => {
  const poes = {
    uuid: "fam-1", name: "The Poe Family", color: "#7cc4ff",
    createdAt: "2026-07-30T10:00:00Z",
  };

  it("round-trips a family and its server id", async () => {
    const repo = await openRepo();
    await repo.add(poes);
    expect((await repo.get("fam-1"))!.name).toBe("The Poe Family");
    // What the engine stamps after a push: both the id and the sync time.
    // syncedAt is what settles pendingSync — an edit clears it while the
    // server id stays, and the family queues again.
    const claimed = await repo.update("fam-1", {
      serverId: 4,
      syncedAt: "2026-08-21T18:00:00Z",
    });
    expect(claimed.serverId).toBe(4);
    expect(await repo.pendingSync()).toEqual([]);
    await repo.update("fam-1", { notes: "edited", syncedAt: undefined });
    expect((await repo.pendingSync()).map((f) => f.uuid)).toEqual(["fam-1"]);
  });

  it("queues a family until the server has it", async () => {
    const repo = await openRepo();
    await repo.add(poes);
    expect((await repo.pendingSync()).map((f) => f.uuid)).toEqual(["fam-1"]);
  });

  it("removes on request", async () => {
    const repo = await openRepo();
    await repo.add(poes);
    await repo.remove("fam-1");
    expect(await repo.get("fam-1")).toBeNull();
    expect(await repo.list()).toEqual([]);
  });
});

describe.each([
  ["memory", async () => new MemoryLabelRepository()],
  ["sqlite", () => SqliteLabelRepository.open(freshName())],
])("LabelRepository (%s)", (_kind, openRepo) => {
  const alarm = {
    uuid: "lab-1", captureUuid: "cap-1", callType: "alarm call",
    species: "American Crow", startSec: 1.5, endSec: 3.25,
    configVersion: 47, fromDetection: true, createdAt: "2026-07-30T10:00:00Z",
  };

  it("round-trips a label with its provenance", async () => {
    const repo = await openRepo();
    await repo.add(alarm);
    const [stored] = await repo.forCapture("cap-1");
    expect(stored.callType).toBe("alarm call");
    expect(stored.configVersion).toBe(47);
    expect(stored.fromDetection).toBe(true);
    expect(stored.startSec).toBe(1.5);
  });

  it("pending until the server confirms, forgettable when servers change", async () => {
    const repo = await openRepo();
    await repo.add(alarm);
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.update("lab-1", { serverId: 12, syncedAt: "2026-07-30T11:00:00Z" });
    expect(await repo.pendingSync()).toEqual([]);
    await repo.forgetServerState();
    expect((await repo.pendingSync()).length).toBe(1);
  });

  it("finds labels by call type and removes them", async () => {
    const repo = await openRepo();
    await repo.add(alarm);
    await repo.add({ ...alarm, uuid: "lab-2", callType: "song" });
    expect((await repo.byCallType("song")).map((l) => l.uuid)).toEqual(["lab-2"]);
    await repo.remove("lab-1");
    expect(await repo.forCapture("cap-1")).toHaveLength(1);
  });
});

describe.each([
  ["memory", async () => new MemoryContextRepository()],
  ["sqlite", () => SqliteContextRepository.open(freshName())],
])("ContextRepository (%s)", (_kind, openRepo) => {
  const dog = {
    uuid: "ctx-1", captureUuid: "cap-1", labelUuid: "lab-1",
    key: "dog_visible", startSec: 1.5, endSec: 3.25,
    createdAt: "2026-07-30T10:00:00Z",
  };

  it("round-trips an event by capture and by label", async () => {
    const repo = await openRepo();
    await repo.add(dog);
    expect((await repo.forCapture("cap-1"))[0].key).toBe("dog_visible");
    expect((await repo.forLabel("lab-1"))[0].uuid).toBe("ctx-1");
  });

  it("keeps a capture-wide event's label honestly absent", async () => {
    // The silent-capture control group: no label to hang off is a real state.
    const repo = await openRepo();
    await repo.add({ ...dog, uuid: "ctx-2", labelUuid: undefined });
    const [stored] = await repo.forCapture("cap-1");
    expect(stored.labelUuid).toBeUndefined();
  });

  it("pending, confirmed, forgotten", async () => {
    const repo = await openRepo();
    await repo.add(dog);
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.update("ctx-1", { serverId: 3, syncedAt: "2026-07-30T11:00:00Z" });
    expect(await repo.pendingSync()).toEqual([]);
    await repo.forgetServerState();
    expect((await repo.pendingSync()).length).toBe(1);
  });
});

describe.each([
  ["memory", async () => new MemorySightingRepository()],
  ["sqlite", () => SqliteSightingRepository.open(freshName())],
])("SightingRepository (%s)", (_kind, openRepo) => {
  const hawk = {
    uuid: "sgt-1", captureUuid: "cap-1", key: "raptor_overhead",
    offsetSec: -90, distanceM: 120, createdAt: "2026-07-30T10:00:00Z",
  };

  it("round-trips a sighting, signed offset included", async () => {
    const repo = await openRepo();
    await repo.add(hawk);
    const [stored] = await repo.forCapture("cap-1");
    expect(stored.offsetSec).toBe(-90);
    expect(stored.distanceM).toBe(120);
  });

  it("pending, confirmed, forgotten, removed", async () => {
    const repo = await openRepo();
    await repo.add(hawk);
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.update("sgt-1", { serverId: 2, syncedAt: "2026-07-30T11:00:00Z" });
    expect(await repo.pendingSync()).toEqual([]);
    await repo.forgetServerState();
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.remove("sgt-1");
    expect(await repo.forCapture("cap-1")).toEqual([]);
  });
});

describe.each([
  ["memory", async () => new MemoryLogRepository()],
  ["sqlite", () => SqliteLogRepository.open(freshName())],
])("LogRepository (%s)", (_kind, openRepo) => {
  const line = (uuid: string, over: Record<string, unknown> = {}) => ({
    uuid, at: "2026-07-30T10:00:00Z", level: "error" as const,
    tag: "recorder", message: "startListening threw", ...over,
  });

  it("appends, reads back newest first, and counts what the server lacks", async () => {
    const repo = await openRepo();
    await repo.append([line("l-1"), line("l-2", { at: "2026-07-30T11:00:00Z", tag: "sync" })]);
    const recent = await repo.recent();
    expect(recent[0].uuid).toBe("l-2");
    expect(await repo.countPending()).toBe(2);
    expect((await repo.tags()).sort()).toEqual(["recorder", "sync"]);
  });

  it("marking synced empties the queue without erasing the log", async () => {
    const repo = await openRepo();
    await repo.append([line("l-1")]);
    await repo.markSynced(["l-1"]);
    expect(await repo.countPending()).toBe(0);
    expect(await repo.recent()).toHaveLength(1);
    await repo.clear();
    expect(await repo.recent()).toHaveLength(0);
  });
});

describe.each([
  ["memory", async () => new MemoryAnalysisCache()],
  ["sqlite", () => SqliteAnalysisCache.open(freshName())],
])("AnalysisCache (%s)", (_kind, openCache) => {
  it("saves, returns and forgets an analysis", async () => {
    const cache = await openCache();
    await cache.save("cap-1", {
      calls: [{ start_sec: 1, end_sec: 2, species: "American Crow",
                call_type: "alarm call", confidence: 0.9 }],
      waveform: [0.1, 1, 0.4],
      duration: 34.2,
    });
    const cached = await cache.get("cap-1");
    expect(cached?.calls).toHaveLength(1);
    expect(cached?.duration).toBe(34.2);
    expect(cached?.fetchedAt).toBeTruthy();
    await cache.forget("cap-1");
    expect(await cache.get("cap-1")).toBeUndefined();
  });
});

describe.each([
  ["memory", async () => new MemoryDictationRepository()],
  ["sqlite", () => SqliteDictationRepository.open(freshName())],
])("DictationRepository (%s)", (_kind, openRepo) => {
  const memo = {
    uuid: "dct-1", captureUuid: "cap-1", audioPath: "/tmp/dictation_1.wav",
    recordedAt: "2026-08-01T18:55:00Z", durationMs: 42_000, bytes: 1_344_044,
    sampleRate: 16_000, channels: 1, inputDevice: "BUILTIN_MIC",
    inputHonoured: true, state: "ready" as const,
  };

  it("round-trips every optional field through add", async () => {
    // The case this whole file exists for: the SQLite INSERT drifting from
    // `update` is how a filmed capture silently lost its video the instant it
    // was saved. A note's microphone fields are the same shape of thing.
    const repo = await openRepo();
    await repo.add(memo);
    const [stored] = await repo.forCapture("cap-1");
    expect(stored.inputDevice).toBe("BUILTIN_MIC");
    expect(stored.inputHonoured).toBe(true);
    expect(stored.durationMs).toBe(42_000);
    expect(stored.sampleRate).toBe(16_000);
    expect(stored.uploadedBytes).toBe(0);
  });

  it("keeps a note that never finished recording out of the queue", async () => {
    // A process killed with the microphone open leaves this row behind, and
    // sending it would upload a 44-byte header as somebody's field note.
    const repo = await openRepo();
    await repo.add({ ...memo, uuid: "dct-2", state: "recording", bytes: 44 });
    expect(await repo.pendingSync()).toEqual([]);
    expect((await repo.stale()).map((d) => d.uuid)).toEqual(["dct-2"]);
  });

  it("pending, resumed, delivered, forgotten, removed", async () => {
    const repo = await openRepo();
    await repo.add(memo);
    expect((await repo.pendingSync()).length).toBe(1);
    // Half sent is still pending — that is what resuming means.
    await repo.update("dct-1", { serverId: 4, uploadedBytes: 600_000 });
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.update("dct-1", { uploadedBytes: 1_344_044 });
    expect(await repo.pendingSync()).toEqual([]);
    // A different server knows none of these ids.
    await repo.forgetServerState();
    expect((await repo.pendingSync()).length).toBe(1);
    await repo.remove("dct-1");
    expect(await repo.forCapture("cap-1")).toEqual([]);
  });

  it("gathers notes across a merge and its parts", async () => {
    // A capture folded into another is never pushed again, so a note on a part
    // would be stranded on the phone forever with nothing saying so.
    const repo = await openRepo();
    await repo.add(memo);
    await repo.add({ ...memo, uuid: "dct-2", captureUuid: "cap-2" });
    const both = await repo.forCaptures(["cap-1", "cap-2"]);
    expect(both.map((d) => d.uuid).sort()).toEqual(["dct-1", "dct-2"]);
    expect(await repo.forCaptures([])).toEqual([]);
  });

  it("lists its audio so the orphan sweep cannot claim one as a capture", async () => {
    // Without this, a memo the app died during is entered as a field recording
    // at the next launch — the recordist's voice in the corpus as bird audio.
    const repo = await openRepo();
    await repo.add(memo);
    expect(await repo.audioPaths()).toEqual(["/tmp/dictation_1.wav"]);
  });
});
