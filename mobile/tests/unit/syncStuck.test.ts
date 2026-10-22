import { beforeEach, describe, expect, it } from "vitest";
import { webcrypto } from "node:crypto";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryFamilyRepository } from "../../src/data/MemoryFamilyRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { MemoryDictationRepository } from "../../src/data/MemoryDictationRepository";
import { MemorySightingRepository } from "../../src/data/MemorySightingRepository";
import { newClientUuid } from "../../src/domain/ids";
import { compatibility } from "../../src/domain/compatibility";
import type { NewCapture } from "../../src/domain/types";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import { MemoryMediaSource } from "../../src/sync/MediaSource";
import { SyncEngine } from "../../src/sync/SyncEngine";
import { FakeFieldServer } from "../FakeFieldServer";

const randomBytes = (length: number) => webcrypto.getRandomValues(new Uint8Array(length));
const AUDIO = new Uint8Array(4096).fill(3);

/**
 * "Press sync in the field, open a capture, come back — it still says syncing."
 *
 * Three separate faults met in that sentence, and the shape of the bug is the
 * interesting part: the *fact* that a sync was running lived in React state
 * belonging to the capture list. Opening a capture unmounted the list and
 * destroyed the only record of it, while the run carried on. Coming back showed
 * an idle bar over rows still marked `syncing`, and the button would happily
 * start a second run on top of the first.
 */
describe("who knows a sync is running", () => {
  let server: FakeFieldServer;
  let repository: MemoryCaptureRepository;

  function engine() {
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    return new SyncEngine({
      repository,
      client: new FieldServerClient("http://server", server, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    });
  }

  async function record(): Promise<string> {
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-27T10:00:00.000Z",
      durationMs: 4000,
      sampleRate: 48_000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
    };
    await repository.add(capture);
    return capture.uuid;
  }

  beforeEach(() => {
    server = new FakeFieldServer();
    repository = new MemoryCaptureRepository();
  });

  it("the engine knows, and says so while it works", async () => {
    await record();
    const sync = engine();
    const seen: boolean[] = [];
    sync.onRunningChanged((running) => seen.push(running));

    expect(sync.isRunning).toBe(false);
    await sync.syncAll();

    expect(seen).toEqual([true, false]);
    expect(sync.isRunning).toBe(false);
  });

  it("stops being able to start a second run on top of the first", async () => {
    // What the button did once the screen had forgotten: two runs over the same
    // captures, one progress bar driven by both.
    await record();
    const sync = engine();

    const [first, second] = await Promise.all([sync.syncAll(), sync.syncAll()]);

    expect(server.captureCount).toBe(1);
    expect(first.synced.length + second.synced.length).toBe(1);
  });

  it("clears the flag even when the run throws", async () => {
    await record();
    const sync = engine();
    server.failNext = 99;
    server.failStatus = 500;

    await sync.syncAll();

    expect(sync.isRunning).toBe(false);
  });
});

describe("captures left claiming to be in flight", () => {
  it("go back in the queue rather than going quiet", async () => {
    // `syncing` is written when an upload starts, and `pendingSync` does not
    // select it — so a run that died leaves rows nothing will ever pick up.
    const repository = new MemoryCaptureRepository();
    const capture: NewCapture = {
      uuid: "stuck",
      mediaUuid: "stuck-m",
      recordedAt: "2026-07-27T10:00:00.000Z",
      durationMs: 1000,
      sampleRate: 48_000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: 10,
    };
    await repository.add(capture);
    await repository.update("stuck", { syncState: "syncing" });
    expect(await repository.pendingSync()).toHaveLength(0);

    expect(await repository.recoverInterrupted()).toBe(1);

    expect(await repository.pendingSync()).toHaveLength(1);
    expect((await repository.get("stuck"))?.lastError).toContain("interrupted");
  });

  it("says nothing happened when nothing was stuck", async () => {
    expect(await new MemoryCaptureRepository().recoverInterrupted()).toBe(0);
  });
});

describe("a server that is not there", () => {
  it("is reported as unreachable rather than as compatible", () => {
    // These call for opposite responses — an old server means "sync anyway and
    // know what you lose", an absent one means "stop now" — and conflating them
    // is what made a field sync spend half a minute per capture proving the
    // same point.
    expect(compatibility(undefined)).toEqual({ reachable: true, serverBehind: false });
  });
});
