/**
 * Host-side checks for the local-first sync path. No device, no Metro.
 *
 * Converted from the original hand-rolled check()/process.exit script; every
 * assertion carried over, one it() per scenario.
 *
 * The behavior under test is what "record offline, sync when asked" actually
 * demands: interruption is normal, so a half-finished sync must resume from
 * where it stopped and must never send the same bytes twice or create the same
 * capture twice.
 */

import { describe, expect, it } from "vitest";

import { MemoryCaptureRepository } from "../../src/data/MemoryCaptureRepository";
import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryFamilyRepository } from "../../src/data/MemoryFamilyRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { MemoryDictationRepository } from "../../src/data/MemoryDictationRepository";
import { MemorySightingRepository } from "../../src/data/MemorySightingRepository";
import { pickFamilyColor } from "../../src/domain/families";
import { newClientUuid } from "../../src/domain/ids";
import { webcrypto } from "node:crypto";
import type { NewCapture } from "../../src/domain/types";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import { MemoryMediaSource } from "../../src/sync/MediaSource";
import { CroppedWavSource, buildWavHeader } from "../../src/sync/CroppedWav";
import { computeWavEnvelope, parseWavHeader } from "../../src/sync/wavEnvelope";
import { cropFromDrag } from "../../src/ui/components/dragCrop";
import { SyncEngine } from "../../src/sync/SyncEngine";
import { FakeFieldServer } from "../FakeFieldServer";

/** The device uses expo-crypto; under Node the platform source is the WebCrypto one. */
const randomBytes = (length: number) => webcrypto.getRandomValues(new Uint8Array(length));

function audio(bytes: number): Uint8Array {
  const data = new Uint8Array(bytes);
  for (let i = 0; i < bytes; i += 1) data[i] = i % 251;
  return data;
}

function sameBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) return false;
  return a.every((value, index) => value === b[index]);
}

function newRecording(path: string, bytes: number, recordedAt: string): NewCapture {
  return {
    uuid: newClientUuid(randomBytes),
    mediaUuid: newClientUuid(randomBytes),
    recordedAt,
    durationMs: 10_000,
    sampleRate: 48000,
    channels: 1,
    audioPath: path,
    bytes,
    latitude: 40.76,
    longitude: -111.89,
  };
}

function harness() {
  const repository = new MemoryCaptureRepository();
  const server = new FakeFieldServer();
  const client = new FieldServerClient("http://127.0.0.1:5100", server, "test-token");
  const media = new MemoryMediaSource();
  // Real in-memory repositories rather than omitted ones. A harness that leaves
  // them out tests an engine that pushes captures and quietly nothing else —
  // which is the exact shape of the bug this constructor now prevents.
  const families = new MemoryFamilyRepository();
  const labels = new MemoryLabelRepository();
  const context = new MemoryContextRepository();
  const sightings = new MemorySightingRepository();
  const dictations = new MemoryDictationRepository();
  const engine = new SyncEngine({
    repository, client, media, rawMedia: media, families, labels, context,
    sightings, dictations,
    locationPrecision: () => "exact" as const,
  });
  return {
    repository, server, client, media, families, labels, context, sightings,
    dictations, engine,
  };
}

describe("local-first sync", () => {

it("a clean sync of one capture", async () => {
    const { repository, server, media, engine } = harness();
    const bytes = audio(700_000);
    media.put("/data/a.wav", bytes);
    const capture = await repository.add(newRecording("/data/a.wav", bytes.byteLength, "2026-07-24T10:00:00Z"));

    const outcome = await engine.syncAll({ chunkBytes: 256 * 1024 });
    const stored = await repository.get(capture.uuid);

    expect(outcome.synced.length === 1, "a clean sync reports the capture as synced").toBe(true);
    expect(outcome.failed.length === 0, "nothing failed").toBe(true);
    expect(stored!.syncState === "synced", "the record ends in the synced state").toBe(true);
    expect(sameBytes(server.stored.get(1)!, bytes), "the server received every byte").toBe(true);
    expect(stored!.uploadedBytes === bytes.byteLength, "uploadedBytes matches the file size").toBe(true);
    expect(server.uploadPuts().length === 3, "it took 3 PUTs at 256 KiB").toBe(true);
    expect((await repository.pendingSync()).length === 0, "a synced capture is no longer pending").toBe(true);
});

it("an idle-mode capture tells the server the trigger pressed the button", async () => {
    // The whole point of the flag: an unattended recording must not land on
    // the server looking like a witnessed one. Sent at create, because how a
    // recording started is a fact about the recording rather than an edit.
    const { repository, server, media, engine } = harness();
    const bytes = audio(100_000);
    media.put("/data/auto.wav", bytes);
    await repository.add({
      ...newRecording("/data/auto.wav", bytes.byteLength, "2026-08-15T19:12:00Z"),
      trigger: "auto",
    });

    await engine.syncAll({ chunkBytes: 256 * 1024 });

    expect(server.lastCapture?.trigger, "the create body carries trigger=auto").toBe("auto");
});

it("a deliberate capture sends no trigger at all", async () => {
    // Undefined, not "manual": null-means-nobody-said is the convention, and
    // JSON drops the undefined so the field never appears on the wire.
    const { repository, server, media, engine } = harness();
    const bytes = audio(100_000);
    media.put("/data/manual.wav", bytes);
    await repository.add(newRecording("/data/manual.wav", bytes.byteLength, "2026-08-15T19:13:00Z"));

    await engine.syncAll({ chunkBytes: 256 * 1024 });

    expect(server.lastCapture?.trigger, "no trigger field on a manual capture").toBeUndefined();
});

it("an interrupted upload resumes instead of restarting", async () => {
    const { repository, server, media, engine } = harness();
    const bytes = audio(700_000);
    media.put("/data/b.wav", bytes);
    const capture = await repository.add(newRecording("/data/b.wav", bytes.byteLength, "2026-07-24T10:00:00Z"));

    // Let the capture, the media slot and one chunk through, then drop the link.
    server.failNext = 0;
    const first = await (async () => {
      server.failStatus = 0;
      // 3 successful requests: create capture, create media, first chunk.
      const original = server.failNext;
      server.failNext = original;
      return engine.syncAll({ chunkBytes: 256 * 1024, onProgress: () => {
        if (server.uploadPuts().length === 1) server.failNext = 1;
      } });
    })();

    expect(first.failed.length === 1, "the interrupted run reports a failure").toBe(true);
    const midway = await repository.get(capture.uuid);
    expect(midway!.syncState === "failed", "the failed capture is retryable (state failed)").toBe(true);
    expect(midway!.uploadedBytes > 0, "progress was remembered, not discarded").toBe(true);
    expect(midway!.serverCaptureId === 1, "the server id was remembered").toBe(true);

    const putsBefore = server.uploadPuts().length;
    const second = await engine.syncAll({ chunkBytes: 256 * 1024 });
    const done = await repository.get(capture.uuid);

    expect(second.synced.length === 1 && done!.syncState === "synced", "the retry completes the capture").toBe(true);
    expect(sameBytes(server.stored.get(1)!, bytes), "the file on the server is byte-identical").toBe(true);
    expect(server.uploadPuts().length - putsBefore < 3, "the retry sent only the remaining chunks").toBe(true);
    expect(server.captureCount === 1, "no capture was duplicated across the two runs").toBe(true);
    expect(done!.serverCaptureId === 1, "the retry reused the remembered server id").toBe(true);
    expect(server.requests.filter((r) => r.path === "/api/captures" && r.method === "POST").length === 1, "the retry did not even re-POST the capture").toBe(true);
});

it("re-syncing a landed capture does not re-open the sealed upload", async () => {
    // Capture 153, "Fledgling annoys his dad", 2026-08-03. Its audio uploaded
    // cleanly; then a spoken note recorded against it made the capture pending
    // again. The second run adopted the media slot's byte count — by then the
    // FLAC size, a little over a quarter of the WAV — and resumed from there
    // into an upload the server had already sealed. It answered 400, and
    // because `pendingSync` re-selects a failed row, the capture failed on
    // every run from then on while the recording sat safely on the server.
    const { repository, server, media, engine } = harness();
    const bytes = audio(700_000);
    media.put("/data/fledgling.wav", bytes);
    const capture = await repository.add(
      newRecording("/data/fledgling.wav", bytes.byteLength, "2026-08-03T02:19:47Z"));

    await engine.syncAll({ chunkBytes: 256 * 1024 });
    const putsWhenLanded = server.uploadPuts().length;

    // Any edit the server holds a copy of makes it pending again — the note was
    // one route in, renaming it at the desk is another.
    await repository.update(capture.uuid, { name: "Fledgling annoys his dad" });
    expect((await repository.pendingSync()).length === 1, "an edit re-queues a synced capture").toBe(true);

    const second = await engine.syncAll({ chunkBytes: 256 * 1024 });
    const stored = await repository.get(capture.uuid);

    expect(second.failed.length === 0, "the second run does not fail the capture").toBe(true);
    expect(stored!.syncState === "synced", "it ends synced rather than failed").toBe(true);
    expect(server.uploadPuts().length === putsWhenLanded, "and sends no byte at the finished upload").toBe(true);
    expect(sameBytes(server.stored.get(1)!, bytes), "the recording on the server is untouched").toBe(true);
    expect((await repository.pendingSync()).length === 0, "so it leaves the queue instead of retrying forever").toBe(true);
});

it("the server's byte count wins over a stale local one", async () => {
    const { repository, server, media, engine } = harness();
    const bytes = audio(300_000);
    media.put("/data/c.wav", bytes);
    const capture = await repository.add(newRecording("/data/c.wav", bytes.byteLength, "2026-07-24T10:00:00Z"));
    // Pretend a previous run believed it had sent everything, but the server
    // never committed it — the classic lost-response case.
    await repository.update(capture.uuid, { uploadedBytes: bytes.byteLength });

    await engine.syncAll({ chunkBytes: 256 * 1024 });
    expect(sameBytes(server.stored.get(1)!, bytes), "a stale local offset is corrected from the server").toBe(true);
});

it("a permanent error is recorded, not retried forever", async () => {
    const { repository, server, media, engine } = harness();
    const bytes = audio(1000);
    media.put("/data/d.wav", bytes);
    const capture = await repository.add(newRecording("/data/d.wav", bytes.byteLength, "2026-07-24T10:00:00Z"));
    server.failStatus = 400;
    server.failNext = 1;

    const outcome = await engine.syncAll();
    const stored = await repository.get(capture.uuid);
    expect(outcome.failed.length === 1 && stored!.syncState === "failed", "a 4xx marks the capture failed").toBe(true);
    expect((stored!.lastError ?? "").includes("400"), "the error is kept for the UI").toBe(true);
    expect(stored!.attempts === 1, "the attempt was counted").toBe(true);
});

it("ordering and progress", async () => {
    const { repository, media, engine } = harness();
    media.put("/data/e1.wav", audio(1000));
    media.put("/data/e2.wav", audio(1000));
    const older = await repository.add(newRecording("/data/e1.wav", 1000, "2026-07-24T09:00:00Z"));
    await repository.add(newRecording("/data/e2.wav", 1000, "2026-07-24T11:00:00Z"));

    const pending = await repository.pendingSync();
    expect(pending[0].uuid === older.uuid, "the backlog drains oldest-first").toBe(true);

    const listed = await repository.list();
    expect(listed[0].recordedAt === "2026-07-24T11:00:00Z", "the capture list shows newest-first").toBe(true);

    const fractions: number[] = [];
    await engine.syncAll({ onProgress: (p) => fractions.push(p.fraction) });
    expect(fractions[fractions.length - 1] === 1, "progress finishes at 1").toBe(true);
});

it("analysis is requested only when asked for", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/f.wav", audio(1000));
    await repository.add(newRecording("/data/f.wav", 1000, "2026-07-24T10:00:00Z"));
    await engine.syncAll();
    expect(!server.requests.some((r) => r.path.endsWith("/analyze")), "no analysis is requested by default").toBe(true);

    const second = harness();
    second.media.put("/data/g.wav", audio(1000));
    await second.repository.add(newRecording("/data/g.wav", 1000, "2026-07-24T10:00:00Z"));
    await second.engine.syncAll({ requestAnalysis: true });
    expect(second.server.requests.some((r) => r.path.endsWith("/analyze")), "analysis is requested when asked for").toBe(true);
});

it("pointing at a different server forgets ids that server never minted", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/h.wav", audio(1000));
    const capture = await repository.add(newRecording("/data/h.wav", 1000, "2026-07-24T10:00:00Z"));
    await engine.syncAll();
    expect((await repository.get(capture.uuid))!.syncState === "synced", "synced against the first server").toBe(true);

    await repository.forgetServerState();
    const reset = await repository.get(capture.uuid);
    expect(reset!.serverCaptureId === undefined, "forgetting server state clears the capture id").toBe(true);
    expect(reset!.serverMediaId === undefined, "forgetting server state clears the media id").toBe(true);
    expect(reset!.uploadedBytes === 0, "forgetting server state rewinds the upload offset").toBe(true);
    expect(reset!.syncState === "local", "the capture is pending again").toBe(true);

    // A fresh server must receive the whole capture again, under its own ids.
    const second = harness();
    second.media.put("/data/h.wav", audio(1000));
    const engine2 = new SyncEngine({
      ...second, repository, client: second.client, rawMedia: second.media,
      locationPrecision: () => "exact" as const,
    });
    await engine2.syncAll();
    expect(second.server.captureCount === 1, "it re-uploads cleanly to the new server").toBe(true);
    expect((await repository.get(capture.uuid))!.syncState === "synced", "and ends synced again").toBe(true);
});

it("an HTML error page is reduced to its one useful sentence", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/i.wav", audio(1000));
    const capture = await repository.add(newRecording("/data/i.wav", 1000, "2026-07-24T10:00:00Z"));
    server.failStatus = 403;
    server.failHtml = true;
    server.failNext = 1;
    await engine.syncAll();
    const stored = await repository.get(capture.uuid);
    expect((stored!.lastError ?? "").includes("not your capture"), "an HTML error is reduced to its message").toBe(true);
    expect(!(stored!.lastError ?? "").includes("<html"), "and the markup is not shown").toBe(true);
});

it("a capture pointing at another identity's row heals itself", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/j.wav", audio(1000));
    const capture = await repository.add(newRecording("/data/j.wav", 1000, "2026-07-24T10:00:00Z"));
    // Stand in for a row minted under an enrollment this device no longer has.
    await repository.update(capture.uuid, { serverCaptureId: 999, serverMediaId: 998 });
    server.forbidCaptureIds.add(999);

    const outcome = await engine.syncAll();
    const healed = await repository.get(capture.uuid);

    expect(outcome.synced.length === 1, "a stale server link does not leave the capture failed").toBe(true);
    expect(healed!.syncState === "synced", "it ends synced").toBe(true);
    expect(healed!.serverCaptureId === 1, "under a freshly minted server id").toBe(true);
    expect(server.stored.get(1)!.byteLength === 1000, "and the audio actually landed").toBe(true);
});

it("a description rides along with the capture", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/k.wav", audio(1000));
    const capture = await repository.add(newRecording("/data/k.wav", 1000, "2026-07-24T10:00:00Z"));

    await engine.syncAll();
    expect(server.observations.size === 0, "no observation is sent when there is no description").toBe(true);

    await repository.update(capture.uuid, {
      description: "Edgar alone on the wire, calling.",
      descriptionUuid: "desc-1",
      descriptionUpdatedAt: "2026-07-24T11:00:00Z",
      syncState: "local",
    });
    await engine.syncAll();

    expect(server.observations.size === 1, "the description reaches the server").toBe(true);
    expect(server.observations.get("desc-1")?.body === "Edgar alone on the wire, calling.", "with the text as written").toBe(true);
    const afterFirst = await repository.get(capture.uuid);
    expect(afterFirst!.descriptionSyncedBody !== undefined, "and is marked as sent").toBe(true);

    // Syncing again with nothing changed must not re-send it.
    await repository.update(capture.uuid, { syncState: "local" });
    await engine.syncAll();
    expect(server.observations.size === 1, "an unchanged description is not re-sent").toBe(true);

    // Editing it must update the same note, not add a second.
    await repository.update(capture.uuid, {
      description: "Edgar alone, then two returned four minutes later.",
      descriptionUpdatedAt: "2026-07-24T12:00:00Z",
      syncState: "local",
    });
    await engine.syncAll();
    expect(server.observations.size === 1, "an edit does not create a second observation").toBe(true);
    expect(server.observations.get("desc-1")?.body.endsWith("four minutes later.") === true, "and the edited text wins").toBe(true);
});

it("a capture with video uploads both files", async () => {
    const { repository, server, media, engine } = harness();
    const wav = audio(50_000);
    const mp4 = audio(400_000);
    media.put("/data/l.wav", wav);
    media.put("/data/l.mp4", mp4);
    const capture = await repository.add({
      ...newRecording("/data/l.wav", wav.byteLength, "2026-07-24T10:00:00Z"),
      videoPath: "/data/l.mp4",
      videoBytes: mp4.byteLength,
      videoMediaUuid: "vid-1",
      videoUploadedBytes: 0,
    });

    const fractions: number[] = [];
    const outcome = await engine.syncAll({
      chunkBytes: 64 * 1024,
      onProgress: (p) => fractions.push(p.runFraction),
    });
    const stored = await repository.get(capture.uuid);

    expect(outcome.synced.length === 1 && stored!.syncState === "synced", "the capture syncs").toBe(true);
    expect(server.stored.size === 2, "two media slots exist server-side").toBe(true);
    expect(sameBytes(server.stored.get(1)!, wav), "the audio landed intact").toBe(true);
    expect(sameBytes(server.stored.get(2)!, mp4), "the video landed intact").toBe(true);
    expect(stored!.videoUploadedBytes === mp4.byteLength, "the video's byte count is remembered").toBe(true);
    // The video is 8x the audio; if progress ignored it the bar would hit 1
    // while most of the bytes were still to go.
    expect(fractions.filter((f) => f >= 1).length === 1, "progress accounts for the video, not just the audio").toBe(true);
});

it("stopping a run mid-upload leaves the backlog honest", async () => {
    const { repository, server, media, engine } = harness();
    const bytes = audio(700_000);
    media.put("/data/m.wav", bytes);
    const capture = await repository.add(newRecording("/data/m.wav", bytes.byteLength, "2026-07-24T10:00:00Z"));

    // Stop it after the first chunk, the way the Stop button does mid-run.
    const outcome = await engine.syncAll({
      chunkBytes: 256 * 1024,
      onProgress: () => {
        if (server.uploadPuts().length === 1) engine.cancel();
      },
    });
    const stopped = await repository.get(capture.uuid);

    expect(outcome.canceled, "a stopped run says so").toBe(true);
    expect(outcome.synced.length === 0, "a stopped capture is not reported as synced").toBe(true);
    expect(outcome.failed.length === 0, "nor as failed — nothing went wrong").toBe(true);
    expect(stopped!.syncState === "local", "the stopped capture is pending again").toBe(true);
    expect((await repository.pendingSync()).length === 1, "it is picked up by the next run").toBe(true);
    expect(stopped!.attempts === 0, "stopping does not burn a retry attempt").toBe(true);
    expect(stopped!.lastError === undefined, "and leaves no error for the UI to show").toBe(true);
    expect(stopped!.uploadedBytes > 0, "the bytes that landed are remembered").toBe(true);
    expect(stopped!.uploadedBytes < bytes.byteLength, "it did not upload the whole file").toBe(true);

    // The point of all of the above: resuming works and costs only the rest.
    const putsBefore = server.uploadPuts().length;
    const resumed = await engine.syncAll({ chunkBytes: 256 * 1024 });
    const done = await repository.get(capture.uuid);
    expect(resumed.synced.length === 1, "resuming after a stop completes the capture").toBe(true);
    expect(done!.syncState === "synced", "it ends synced").toBe(true);
    expect(sameBytes(server.stored.get(1)!, bytes), "the file is byte-identical").toBe(true);
    expect(server.captureCount === 1, "no capture was duplicated by the stop").toBe(true);
    expect(server.uploadPuts().length - putsBefore < 3, "the resume sent only what was left").toBe(true);
});

it("stopping between captures leaves the later ones untouched", async () => {
    const { repository, media, engine } = harness();
    media.put("/data/n1.wav", audio(1000));
    media.put("/data/n2.wav", audio(1000));
    const first = await repository.add(newRecording("/data/n1.wav", 1000, "2026-07-24T09:00:00Z"));
    const second = await repository.add(newRecording("/data/n2.wav", 1000, "2026-07-24T10:00:00Z"));

    const outcome = await engine.syncAll({
      onProgress: (p) => {
        if (p.captureUuid === first.uuid) engine.cancel();
      },
    });

    expect(outcome.canceled, "the run reports being stopped").toBe(true);
    expect((await repository.get(second.uuid))!.syncState === "local", "the untouched capture is still pending").toBe(true);
    expect((await repository.pendingSync()).length === 2, "both captures are still in the backlog").toBe(true);
});

it("WAV parsing, envelope and cropping", async () => {
    // A 2-second 48 kHz mono 16-bit WAV, quiet then loud, with a LIST chunk
    // wedged before the data — exactly what ffmpeg emits for seeded captures.
    const sampleRate = 48000;
    const frames = sampleRate * 2;
    const pcm = new Uint8Array(frames * 2);
    const pcmView = new DataView(pcm.buffer);
    for (let i = 0; i < frames; i += 1) {
      const amp = i < frames / 2 ? 1000 : 30000; // second half much louder
      pcmView.setInt16(i * 2, amp, true);
    }
    const list = new Uint8Array(16); // 8-byte header + 8 bytes of junk
    const enc = (t: string) => Array.from(t).map((c) => c.charCodeAt(0));
    list.set(enc("LIST"), 0);
    new DataView(list.buffer).setUint32(4, 8, true);
    list.set(enc("INFOxxxx"), 8);

    const header = buildWavHeader(
      { sampleRate, channels: 1, bitsPerSample: 16, dataOffset: 0, dataBytes: pcm.byteLength },
      pcm.byteLength,
    );
    // Splice the LIST chunk in between `fmt ` and `data`.
    const withList = new Uint8Array(36 + list.byteLength + 8 + pcm.byteLength);
    withList.set(header.subarray(0, 36), 0);
    withList.set(list, 36);
    withList.set(header.subarray(36, 44), 36 + list.byteLength);
    withList.set(pcm, 36 + list.byteLength + 8);

    const files = new MemoryMediaSource();
    files.put("/data/w.wav", withList);

    const format = parseWavHeader(withList.subarray(0, 4096));
    expect(format.sampleRate === 48000, "header parse finds the real sample rate").toBe(true);
    expect(format.dataOffset === 36 + list.byteLength + 8, "header parse skips the LIST chunk").toBe(true);
    expect(format.dataBytes === sampleRate * 2 * 2, "data chunk holds the full two seconds").toBe(true);

    const env = await computeWavEnvelope(files, "/data/w.wav", 10);
    expect(env.peaks.length === 10, "envelope has the requested buckets").toBe(true);
    expect(Math.max(...env.peaks) === 1, "envelope is normalised to 1").toBe(true);
    expect(env.peaks[0] < 0.2 && env.peaks[9] === 1, "envelope shows the quiet half as quiet").toBe(true);

    // Crop to the loud second only.
    const cropped = new CroppedWavSource(files, () => ({ startSec: 1, endSec: 2 }));
    const size = await cropped.size("/data/w.wav");
    expect(size === 44 + sampleRate * 2, "cropped size is header + one second of PCM").toBe(true);

    const whole = await cropped.read("/data/w.wav", 0, size);
    const croppedFormat = parseWavHeader(whole);
    expect(croppedFormat.sampleRate === 48000, "cropped output is a valid WAV").toBe(true);
    expect(croppedFormat.dataBytes === sampleRate * 2, "cropped output declares one second").toBe(true);

    const firstSample = new DataView(whole.buffer, whole.byteOffset + croppedFormat.dataOffset).getInt16(0, true);
    expect(firstSample === 30000, "cropped audio starts at the loud half").toBe(true);

    // Chunked reads must reassemble identically — the upload path reads in pieces.
    const pieces: number[] = [];
    for (let off = 0; off < size; off += 7000) {
      const part = await cropped.read("/data/w.wav", off, 7000);
      pieces.push(...part);
    }
    expect(pieces.length === size && pieces[0] === whole[0], "chunked reads match a single read").toBe(true);
    expect(pieces[44] === whole[44] && pieces[100] === whole[100], "chunked read across the header/PCM join is correct").toBe(true);

    // The original must be untouched.
    expect((await files.size("/data/w.wav")) === withList.byteLength, "cropping never modifies the file on disk").toBe(true);
});

it("dragging a trim handle", async () => {
    // 20-second recording on a 200pt track: 10pt per second.
    const anchor = { start: 0, end: 20, width: 200, span: 20 };

    const half = cropFromDrag(anchor, "start", 50);
    expect(Math.abs(half.start - 5) < 1e-9, "dragging start 50pt moves it 5s").toBe(true);
    expect(half.end === 20, "dragging start leaves end alone").toBe(true);

    // The bug that shipped: a second move must be measured from the anchor, not
    // from where the handle already moved to. Same total dx => same position.
    const step1 = cropFromDrag(anchor, "start", 50);
    const step2 = cropFromDrag(anchor, "start", 50);
    expect(step1.start === step2.start, "repeating the same drag does not compound").toBe(true);
    const further = cropFromDrag(anchor, "start", 100);
    expect(Math.abs(further.start - 10) < 1e-9, "twice the drag is twice the distance, not four times").toBe(true);

    expect(cropFromDrag(anchor, "start", -500).start === 0, "start cannot go below zero").toBe(true);
    expect(cropFromDrag(anchor, "end", 500).end === 20, "end cannot exceed the recording").toBe(true);

    const squeezed = cropFromDrag(anchor, "start", 5000);
    expect(Math.abs(squeezed.start - 19.5) < 1e-9, "start stops half a second before end").toBe(true);
    const squeezedEnd = cropFromDrag({ ...anchor, start: 4 }, "end", -5000);
    expect(Math.abs(squeezedEnd.end - 4.5) < 1e-9, "end stops half a second after start").toBe(true);

    expect(cropFromDrag({ ...anchor, width: 0 }, "start", 80).start === 0, "a zero-width track is ignored rather than dividing by zero").toBe(true);
});

it("families go up before the captures that reference them", async () => {
    const repository = new MemoryCaptureRepository();
    const server = new FakeFieldServer();
    const client = new FieldServerClient("http://127.0.0.1:5100", server, "test-token");
    const media = new MemoryMediaSource();
    const familyRepo = new MemoryFamilyRepository();
    const engine = new SyncEngine({
      repository, client, media, rawMedia: media,
      families: familyRepo,
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact" as const,
    });

    await familyRepo.add({
      uuid: "fam-local-1",
      name: "The Poe Family",
      color: "#7cc4ff",
      createdAt: "2026-07-25T10:00:00Z",
    });
    media.put("/data/f1.wav", audio(1000));
    const capture = await repository.add({
      ...newRecording("/data/f1.wav", 1000, "2026-07-25T10:00:00Z"),
      familyUuid: "fam-local-1",
    });

    await engine.syncAll();

    const order = server.requests.filter((r) => r.method === "POST").map((r) => r.path);
    expect(order.indexOf("/api/families") < order.indexOf("/api/captures"), "the family is created before the capture").toBe(true);
    expect(server.families.size === 1, "the family reached the server once").toBe(true);
    expect(server.captureFamilyId("/api/captures") === 1, "the capture is attached to the server-side family id").toBe(true);
    const storedFamily = await familyRepo.get("fam-local-1");
    expect(storedFamily!.serverId === 1, "the local family remembers its server id").toBe(true);

    // A second sync must not create the family again.
    await repository.update(capture.uuid, { syncState: "local" });
    await engine.syncAll();
    expect(server.families.size === 1, "an already-synced family is not re-created").toBe(true);
});

it("an edited family re-pushes so the server can adopt the change", async () => {
    const repository = new MemoryCaptureRepository();
    const server = new FakeFieldServer();
    const client = new FieldServerClient("http://127.0.0.1:5100", server, "test-token");
    const media = new MemoryMediaSource();
    const familyRepo = new MemoryFamilyRepository();
    const engine = new SyncEngine({
      repository, client, media, rawMedia: media,
      families: familyRepo,
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact" as const,
    });

    await familyRepo.add({
      uuid: "fam-local-2",
      name: "The Red Liners",
      color: "#ef476f",
      createdAt: "2026-08-20T10:00:00Z",
    });
    await engine.syncAll();
    const synced = await familyRepo.get("fam-local-2");
    expect(synced!.syncedAt !== undefined, "first push marks it synced").toBe(true);

    // The description edit clears syncedAt but keeps serverId — the exact
    // state pendingSync once ignored, stranding the edit on the phone.
    await familyRepo.update("fam-local-2", {
      notes: "6th East Park pair",
      syncedAt: undefined,
    });
    await engine.syncAll();
    const familyPosts = server.requests.filter(
      (r) => r.method === "POST" && r.path === "/api/families");
    expect(familyPosts.length === 2, "the edit is pushed again").toBe(true);
    const after = await familyRepo.get("fam-local-2");
    expect(after!.syncedAt !== undefined, "the edit is marked synced").toBe(true);
    expect(after!.serverId === 1, "the server id survives the edit").toBe(true);
});

it("family colours", async () => {
    const first = pickFamilyColor([]);
    expect(first.startsWith("#"), "a new family gets a colour").toBe(true);
    const second = pickFamilyColor([first]);
    expect(second !== first, "a second family gets a different one").toBe(true);
});

it("captures without a family still sync", async () => {
    const { repository, server, media, engine } = harness();
    media.put("/data/f2.wav", audio(1000));
    await repository.add(newRecording("/data/f2.wav", 1000, "2026-07-25T10:00:00Z"));
    const outcome = await engine.syncAll();
    expect(outcome.synced.length === 1 && server.families.size === 0, "family is optional").toBe(true);
});

it("ids are unique", async () => {
    const ids = new Set(Array.from({ length: 5000 }, () => newClientUuid(randomBytes)));
    expect(ids.size === 5000, "client uuids do not collide").toBe(true);
});


});
