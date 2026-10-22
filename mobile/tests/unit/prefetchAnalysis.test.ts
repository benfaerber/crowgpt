import { describe, expect, it, vi } from "vitest";

import { MemoryAnalysisCache } from "../../src/data/MemoryAnalysisCache";
import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { PrefetchAnalysis } from "../../src/sync/PrefetchAnalysis";
import type { FieldServerClient } from "../../src/net/FieldServerClient";
import type { NewCapture } from "../../src/domain/types";

const CALL = { start_sec: 3, end_sec: 4, species: "American Crow" };

function capture(uuid: string): NewCapture {
  return {
    uuid,
    mediaUuid: `${uuid}-media`,
    recordedAt: "2026-07-20T10:00:00.000Z",
    durationMs: 18_000,
    sampleRate: 48_000,
    channels: 1,
    audioPath: `/tmp/${uuid}.wav`,
    bytes: 1024,
  };
}

/** A repository holding captures, some of them synced. */
async function corpus(synced: string[], local: string[] = []) {
  const repository = new MemoryCaptureRepository();
  let serverId = 100;
  for (const uuid of synced) {
    await repository.add(capture(uuid));
    await repository.update(uuid, { serverCaptureId: (serverId += 1) });
  }
  for (const uuid of local) await repository.add(capture(uuid));
  return repository;
}

const client = (analysis: unknown) => ({ analysis }) as unknown as FieldServerClient;

/**
 * Filling the cache before it is needed, which is always somewhere else.
 *
 * The use case this exists for: standing in a park having just recorded
 * something, wanting to play it against a call marked `alarm` in June to decide
 * whether they are the same. A cache that fills as captures are opened has
 * nothing to offer there — the June capture was last opened at a desk.
 */
describe("warming the analysis cache", () => {
  it("stores every synced capture", async () => {
    const cache = new MemoryAnalysisCache();
    const fetch = vi.fn().mockResolvedValue({ calls: [CALL], waveform: [0.5] });

    const outcome = await new PrefetchAnalysis(
      await corpus(["a", "b"]), cache, client(fetch),
    ).run();

    expect(outcome.stored).toBe(2);
    expect((await cache.get("a"))?.calls).toHaveLength(1);
    expect((await cache.get("b"))?.waveform).toEqual([0.5]);
  });

  it("ignores captures that have never synced", async () => {
    // The server has no audio for them, so it has nothing to say about them.
    const fetch = vi.fn().mockResolvedValue({ calls: [CALL], waveform: [0.5] });

    await new PrefetchAnalysis(
      await corpus(["a"], ["never-synced"]), new MemoryAnalysisCache(), client(fetch),
    ).run();

    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("refetches what it already has", async () => {
    // Analysis is re-run whenever the model or the thresholds change, and each
    // time a skip-if-present cache silently becomes the old model's opinion.
    const cache = new MemoryAnalysisCache();
    await cache.save("a", { calls: [], waveform: [0.1] });
    const fetch = vi.fn().mockResolvedValue({ calls: [CALL], waveform: [0.9] });

    await new PrefetchAnalysis(await corpus(["a"]), cache, client(fetch)).run();

    expect((await cache.get("a"))?.calls).toHaveLength(1);
  });

  it("does not store an empty answer over nothing", async () => {
    // A queued job and an analyzed-and-found-nothing capture both come back
    // empty here, and the screen says different things about them. Storing this
    // one would make "not analyzed yet" indistinguishable from "no calls".
    const cache = new MemoryAnalysisCache();
    const fetch = vi.fn().mockResolvedValue({ calls: [], waveform: [] });

    const outcome = await new PrefetchAnalysis(
      await corpus(["a"]), cache, client(fetch),
    ).run();

    expect(outcome.pending).toBe(1);
    expect(await cache.get("a")).toBeUndefined();
  });

  it("keeps going when one capture fails", async () => {
    const cache = new MemoryAnalysisCache();
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("gone"))
      .mockResolvedValue({ calls: [CALL], waveform: [0.5] });

    const outcome = await new PrefetchAnalysis(
      await corpus(["a", "b"]), cache, client(fetch),
    ).run();

    expect(outcome.failed).toBe(1);
    expect(outcome.stored).toBe(1);
  });

  it("gives up when the server is plainly not there", async () => {
    // A phone out of range would otherwise grind through three hundred doomed
    // requests every time the app opens.
    const fetch = vi.fn().mockRejectedValue(new Error("network error"));

    const outcome = await new PrefetchAnalysis(
      await corpus(["a", "b", "c", "d", "e", "f"]),
      new MemoryAnalysisCache(),
      client(fetch),
    ).run();

    expect(outcome.offline).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("does not mistake one bad capture for a missing server", async () => {
    // A row minted under a previous enrollment answers 404 while everything
    // around it is fine.
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("404"))
      .mockResolvedValue({ calls: [CALL], waveform: [0.5] });

    const outcome = await new PrefetchAnalysis(
      await corpus(["a", "b", "c", "d"]), new MemoryAnalysisCache(), client(fetch),
    ).run();

    expect(outcome.offline).toBe(false);
    expect(outcome.stored).toBe(3);
  });

  it("reports progress against what it will actually fetch", async () => {
    const seen: string[] = [];
    const fetch = vi.fn().mockResolvedValue({ calls: [CALL], waveform: [0.5] });

    await new PrefetchAnalysis(
      await corpus(["a", "b"], ["local"]), new MemoryAnalysisCache(), client(fetch),
    ).run((done, total) => seen.push(`${done}/${total}`));

    expect(seen).toEqual(["1/2", "2/2"]);
  });
});
