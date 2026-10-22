import { beforeEach, describe, expect, it } from "vitest";
import { webcrypto } from "node:crypto";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryFamilyRepository } from "../../src/data/MemoryFamilyRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { MemoryDictationRepository } from "../../src/data/MemoryDictationRepository";
import { MemorySightingRepository } from "../../src/data/MemorySightingRepository";
import { newClientUuid } from "../../src/domain/ids";
import type { NewCapture } from "../../src/domain/types";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import { MemoryMediaSource } from "../../src/sync/MediaSource";
import { SyncEngine } from "../../src/sync/SyncEngine";
import { FakeFieldServer } from "../FakeFieldServer";

const randomBytes = (length: number) => webcrypto.getRandomValues(new Uint8Array(length));

/**
 * Tagging a family *after* the capture has already uploaded.
 *
 * The common case — a family is chosen back at the desk, not in the moment —
 * and the one that was silently broken. `family_id` was only ever sent while
 * creating the capture, so a re-sync skipped it entirely, sent nothing, and
 * then recorded the edit as delivered.
 */
describe("re-tagging an uploaded capture", () => {
  let server: FakeFieldServer;
  let repository: MemoryCaptureRepository;
  let families: MemoryFamilyRepository;
  let engine: SyncEngine;

  const AUDIO = new Uint8Array(2048).fill(7);

  beforeEach(async () => {
    server = new FakeFieldServer();
    repository = new MemoryCaptureRepository();
    families = new MemoryFamilyRepository();
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    engine = new SyncEngine({
      repository,
      client: new FieldServerClient("http://server", server, "tok"),
      media,
      rawMedia: media,
      families,
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    });
  });

  async function recordAndSync(): Promise<string> {
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-25T18:00:00Z",
      durationMs: 2000,
      sampleRate: 48000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
    };
    await repository.add(capture);
    await engine.syncAll({ requestAnalysis: false });
    return capture.uuid;
  }

  it("uploads with no family when none was chosen", async () => {
    const uuid = await recordAndSync();
    const synced = await repository.get(uuid);
    expect(synced?.syncState).toBe("synced");
    expect(synced?.familyUuid).toBeUndefined();
  });

  it("makes the capture pending again once tagged", async () => {
    const uuid = await recordAndSync();
    const family = await families.add({
      uuid: newClientUuid(randomBytes),
      name: "The Poe Family",
      color: "#4dd6c8",
      createdAt: "2026-07-25T19:00:00Z",
    });

    await repository.update(uuid, { familyUuid: family.uuid });

    expect(await repository.pendingSync()).toHaveLength(1);
  });

  it("sends the family to the server on the next sync", async () => {
    const uuid = await recordAndSync();
    const family = await families.add({
      uuid: newClientUuid(randomBytes),
      name: "The Poe Family",
      color: "#4dd6c8",
      createdAt: "2026-07-25T19:00:00Z",
    });
    await repository.update(uuid, { familyUuid: family.uuid });

    await engine.syncAll({ requestAnalysis: false });

    // The whole point: a PATCH went out, because the create path cannot run
    // twice and was the only place this field was ever sent.
    const patched = server.requests.filter((r) => r.method === "PATCH");
    expect(patched).toHaveLength(1);
  });

  it("does not re-upload the audio to deliver a tag", async () => {
    const uuid = await recordAndSync();
    const uploadsBefore = server.uploadPuts().length;
    const family = await families.add({
      uuid: newClientUuid(randomBytes),
      name: "The Poe Family",
      color: "#4dd6c8",
      createdAt: "2026-07-25T19:00:00Z",
    });
    await repository.update(uuid, { familyUuid: family.uuid });

    await engine.syncAll({ requestAnalysis: false });

    // Idempotency is what makes the re-push cheap: the server already holds
    // every byte, so the upload loop must not run.
    expect(server.uploadPuts()).toHaveLength(uploadsBefore);
  });

  it("settles afterwards instead of syncing forever", async () => {
    const uuid = await recordAndSync();
    const family = await families.add({
      uuid: newClientUuid(randomBytes),
      name: "The Poe Family",
      color: "#4dd6c8",
      createdAt: "2026-07-25T19:00:00Z",
    });
    await repository.update(uuid, { familyUuid: family.uuid });
    await engine.syncAll({ requestAnalysis: false });

    expect(await repository.pendingSync()).toHaveLength(0);
  });

  it("delivers a note corrected after upload", async () => {
    const uuid = await recordAndSync();
    await repository.update(uuid, { notes: "two returned four minutes later" });

    await engine.syncAll({ requestAnalysis: false });

    expect(server.requests.filter((r) => r.method === "PATCH")).toHaveLength(1);
  });

  it("does not PATCH a capture that has not been edited", async () => {
    // A re-sync triggered by something else must not send a pointless write.
    const uuid = await recordAndSync();
    await repository.update(uuid, { syncState: "failed" });

    await engine.syncAll({ requestAnalysis: false });

    expect(server.requests.filter((r) => r.method === "PATCH")).toHaveLength(0);
  });
});
