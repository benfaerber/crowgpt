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
import { SyncEngine, type SyncDeps } from "../../src/sync/SyncEngine";
import { FakeFieldServer } from "../FakeFieldServer";

const randomBytes = (length: number) => webcrypto.getRandomValues(new Uint8Array(length));
const AUDIO = new Uint8Array(2048).fill(7);

/**
 * A sync engine pushes everything it was wired with, and nothing it wasn't.
 *
 * The bug these exist for: the engine's repositories used to be optional
 * positional parameters, and each push began `if (!this.labels) return`. An
 * under-wired engine therefore uploaded audio perfectly and dropped every label
 * on the floor in silence. It happened for real — rebuilding the client after a
 * server change passed four of six dependencies — and neither the compiler nor
 * any test had an opinion, because "pushed no labels" and "had no labels to
 * push" are the same observation from outside.
 *
 * So these tests assert on what *reached the server*, not on what was called.
 */
describe("sync engine wiring", () => {
  let server: FakeFieldServer;
  let deps: SyncDeps;
  let captureUuid: string;

  function build(target: FakeFieldServer): SyncDeps {
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    return {
      repository: new MemoryCaptureRepository(),
      client: new FieldServerClient("http://server", target, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    };
  }

  /** One capture, one label on it, one thing witnessed during that call. */
  async function record(into: SyncDeps): Promise<string> {
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-26T09:00:00Z",
      durationMs: 2000,
      sampleRate: 48000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
    };
    await into.repository.add(capture);

    const labelUuid = newClientUuid(randomBytes);
    await into.labels.add({
      uuid: labelUuid,
      captureUuid: capture.uuid,
      callType: "alarm call",
      species: "American Crow",
      startSec: 0,
      endSec: 1.5,
      createdAt: "2026-07-26T09:00:05Z",
    });
    await into.context.add({
      uuid: newClientUuid(randomBytes),
      captureUuid: capture.uuid,
      labelUuid,
      key: "dog_visible",
      createdAt: "2026-07-26T09:00:06Z",
    });
    return capture.uuid;
  }

  beforeEach(async () => {
    server = new FakeFieldServer();
    deps = build(server);
    captureUuid = await record(deps);
  });

  it("pushes the label and the context alongside the audio", async () => {
    await new SyncEngine(deps).syncAll();

    expect(server.captureCount).toBe(1);
    expect(server.labels.size).toBe(1);
    expect(server.context.size).toBe(1);
  });

  it("hangs each context event off the call it was the situation for", async () => {
    // Not off the capture. "Crows sing at dogs" is what per-capture tagging
    // reports when a capture holds both a song and an alarm call.
    await new SyncEngine(deps).syncAll();

    const label = [...server.labels.values()][0];
    expect([...server.context.values()][0].label_id).toBe(label.id);
  });

  it("keeps pushing labels after the server changes", async () => {
    // The original defect, end to end: the app is pointed at a different
    // server, the engine is rebuilt for it, and labels must still go up.
    await new SyncEngine(deps).syncAll();

    const moved = new FakeFieldServer();
    const next: SyncDeps = { ...deps, client: new FieldServerClient("http://other", moved, "tok") };
    await next.repository.forgetServerState();
    await next.labels.forgetServerState();
    await next.context.forgetServerState();
    await new SyncEngine(next).syncAll();

    expect(moved.captureCount).toBe(1);
    expect(moved.labels.size).toBe(1);
    expect(moved.context.size).toBe(1);
  });

  it("does not re-send a label the server already holds", async () => {
    const engine = new SyncEngine(deps);
    await engine.syncAll();
    await engine.syncAll();

    expect(server.labels.size).toBe(1);
    expect(server.requests.filter((r) => r.path.endsWith("/labels")).length).toBe(1);
  });

  it("holds back a context event whose label has not landed", async () => {
    // Its server-side row names a label id, so an event that overtook its label
    // would have nothing to attach to. It waits for the next run instead of
    // going up unattached — the failure mode that loses which call it described.
    const orphan = newClientUuid(randomBytes);
    await deps.context.add({
      uuid: orphan,
      captureUuid,
      labelUuid: "a-label-that-never-synced",
      key: "human_walks_through",
      createdAt: "2026-07-26T09:00:07Z",
    });

    await new SyncEngine(deps).syncAll();

    expect(server.context.size).toBe(1);
    const held = (await deps.context.forCapture(captureUuid)).find((e) => e.uuid === orphan);
    expect(held?.serverId).toBeUndefined();
  });
});

/**
 * Out-of-frame sightings sync, and stay out of the ground truth while doing it.
 *
 * The whole design rests on these two never being confused, so the seam where
 * they travel together is exactly where that has to be pinned.
 */
describe("out-of-frame sightings", () => {
  let server: FakeFieldServer;
  let deps: SyncDeps;
  let captureUuid: string;

  function build(target: FakeFieldServer): SyncDeps {
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    return {
      repository: new MemoryCaptureRepository(),
      client: new FieldServerClient("http://server", target, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    };
  }

  beforeEach(async () => {
    server = new FakeFieldServer();
    deps = build(server);
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-26T09:00:00Z",
      durationMs: 2000,
      sampleRate: 48000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
    };
    await deps.repository.add(capture);
    captureUuid = capture.uuid;
    await deps.sightings.add({
      uuid: newClientUuid(randomBytes),
      captureUuid,
      key: "raptor_overhead",
      offsetSec: 300,
      notes: "2 hawks from the window, a block away",
      createdAt: "2026-07-26T09:06:00Z",
    });
  });

  it("uploads the sighting with its offset", async () => {
    await new SyncEngine(deps).syncAll();

    expect(server.sightings.size).toBe(1);
    expect([...server.sightings.values()][0].offset_sec).toBe(300);
  });

  it("does not need a label first, unlike context", async () => {
    // A sighting is about the recording, not about one call in it. Requiring a
    // label would mean you could not log one on a capture nobody has labelled.
    await new SyncEngine(deps).syncAll();

    expect(server.labels.size).toBe(0);
    expect(server.sightings.size).toBe(1);
  });

  it("never arrives as a context event", async () => {
    await new SyncEngine(deps).syncAll();

    expect(server.context.size).toBe(0);
    expect(server.requests.some((r) => r.path.endsWith("/context"))).toBe(false);
  });

  it("does not re-send one the server already holds", async () => {
    const engine = new SyncEngine(deps);
    await engine.syncAll();
    await engine.syncAll();

    expect(server.requests.filter((r) => r.path.endsWith("/sightings")).length).toBe(1);
  });

  it("keeps a sighting before the recording as a negative offset", async () => {
    // "A hawk went over just before he started" is a different claim from
    // "a hawk appeared afterwards", and it is the more interesting one.
    await deps.sightings.add({
      uuid: newClientUuid(randomBytes),
      captureUuid,
      key: "raptor_overhead",
      offsetSec: -90,
      createdAt: "2026-07-26T09:07:00Z",
    });
    await new SyncEngine(deps).syncAll();

    const offsets = [...server.sightings.values()].map((s) => s.offset_sec).sort();
    expect(offsets).toEqual([-90, 300]);
  });
});

/**
 * Confirmed silence, and the capture-level context it unlocks.
 *
 * A recording where nothing was said is the control group. It only counts if it
 * syncs as such — an unreviewed capture and a genuinely quiet one are identical
 * on the wire unless the claim travels with it.
 */
describe("confirmed silence", () => {
  let server: FakeFieldServer;
  let deps: SyncDeps;
  let captureUuid: string;

  beforeEach(async () => {
    server = new FakeFieldServer();
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    deps = {
      repository: new MemoryCaptureRepository(),
      client: new FieldServerClient("http://server", server, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    };
    const capture: NewCapture = {
      uuid: newClientUuid(randomBytes),
      mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-07-26T09:00:00Z",
      durationMs: 2000,
      sampleRate: 48000,
      channels: 1,
      audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
      silentConfirmedAt: "2026-07-26T09:10:00Z",
    };
    await deps.repository.add(capture);
    captureUuid = capture.uuid;
  });

  it("pushes capture-level context with no label to wait for", async () => {
    // The whole point: on a silent recording there is no call to attach to, and
    // the old code skipped any event whose label had not landed — which for
    // these is forever.
    await deps.context.add({
      uuid: newClientUuid(randomBytes),
      captureUuid,
      key: "human_gives_food",
      createdAt: "2026-07-26T09:11:00Z",
    });

    await new SyncEngine(deps).syncAll();

    expect(server.context.size).toBe(1);
    expect([...server.context.values()][0].label_id).toBeUndefined();
  });

  it("still holds back an event that names a label which has not landed", async () => {
    // The general rule has to survive the exception, or context starts arriving
    // unattached on ordinary recordings.
    await deps.context.add({
      uuid: newClientUuid(randomBytes),
      captureUuid,
      labelUuid: "a-label-that-never-synced",
      key: "dog_visible",
      createdAt: "2026-07-26T09:12:00Z",
    });

    await new SyncEngine(deps).syncAll();

    expect(server.context.size).toBe(0);
  });
});

/**
 * A spoken note is the recordist's account taken while it is still fresh, and
 * it is the scarce input the labelling bottleneck waits on. Asserted on what
 * reached the server, for the reason at the top of this file.
 *
 * Its own harness rather than the one above: these need a note and a plain
 * media source, and nothing else, so a fixture that grows for the label tests
 * cannot quietly change what this is proving.
 */
describe("spoken notes reach the server", () => {
  const NOTE = new Uint8Array(1024).fill(3);

  function harness() {
    const server = new FakeFieldServer();
    const media = new MemoryMediaSource();
    media.put("/tmp/a.wav", AUDIO);
    media.put("/tmp/note.wav", NOTE);
    const deps: SyncDeps = {
      repository: new MemoryCaptureRepository(),
      client: new FieldServerClient("http://server", server, "tok"),
      media,
      rawMedia: media,
      families: new MemoryFamilyRepository(),
      labels: new MemoryLabelRepository(),
      context: new MemoryContextRepository(),
      sightings: new MemorySightingRepository(),
      dictations: new MemoryDictationRepository(),
      locationPrecision: () => "exact",
    };
    return { server, deps };
  }

  async function capture(deps: SyncDeps): Promise<string> {
    const uuid = newClientUuid(randomBytes);
    await deps.repository.add({
      uuid, mediaUuid: newClientUuid(randomBytes),
      recordedAt: "2026-08-01T18:50:00Z", durationMs: 2000,
      sampleRate: 48000, channels: 1, audioPath: "/tmp/a.wav",
      bytes: AUDIO.byteLength,
    });
    return uuid;
  }

  const note = (captureUuid: string, patch: Record<string, unknown> = {}) => ({
    uuid: "dct-1", captureUuid, audioPath: "/tmp/note.wav",
    recordedAt: "2026-08-01T18:55:00Z", durationMs: 26_500,
    bytes: NOTE.byteLength, sampleRate: 48_000, channels: 1,
    state: "ready" as const, ...patch,
  });

  it("sends the note alongside the audio", async () => {
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid));

    await new SyncEngine(deps).syncAll();

    expect(server.dictations.size).toBe(1);
    const [sent] = [...server.dictations.values()];
    expect(sent.upload_state).toBe("complete");
    expect(sent.bytes).toBe(NOTE.byteLength);
  });

  it("does not send it twice", async () => {
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid));

    await new SyncEngine(deps).syncAll();
    await new SyncEngine(deps).syncAll();

    expect(server.dictations.size).toBe(1);
  });

  it("sends one added after the capture had already synced", async () => {
    // The trap: pendingSync only selects captures that are local, failed or
    // edited, so without markCaptureDirty a note recorded onto a capture that
    // has already gone up would never be pushed — silently, and permanently.
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await new SyncEngine(deps).syncAll();
    expect(server.dictations.size).toBe(0);

    await deps.dictations.add(note(uuid));
    const row = (await deps.repository.get(uuid))!;
    await deps.repository.update(uuid, { localRevision: (row.localRevision ?? 0) + 1 });
    await new SyncEngine(deps).syncAll();

    expect(server.dictations.size).toBe(1);
  });

  it("never sends one the app died during", async () => {
    // A 44-byte header would upload as a successful sync of an empty note, and
    // the server would queue a job to transcribe silence.
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid, { state: "recording", bytes: 44 }));

    await new SyncEngine(deps).syncAll();

    expect(server.dictations.size).toBe(0);
  });

  it("counts the note in the run's total", async () => {
    // Reported as "0/0" on a real sync: the capture had already gone up, so the
    // run's total was zero while two and a half megabytes of note went with it.
    const { deps } = harness();
    const uuid = await capture(deps);
    await new SyncEngine(deps).syncAll();

    await deps.dictations.add(note(uuid));
    const row = (await deps.repository.get(uuid))!;
    await deps.repository.update(uuid, { localRevision: (row.localRevision ?? 0) + 1 });

    let total = 0;
    await new SyncEngine(deps).syncAll({
      onProgress: (update) => { total = Math.max(total, update.bytesToSend); },
    });

    expect(total).toBeGreaterThanOrEqual(NOTE.byteLength);
  });

  it("brings the transcript back on the next sync", async () => {
    // The one thing that travels down. Without it the card says "sent —
    // waiting for the transcript" forever, which is a promise the app had no
    // way to keep: a transcript is made on the server and the phone has no
    // version of it to be overwritten.
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid));
    await new SyncEngine(deps).syncAll();

    const [sent] = [...server.dictations.values()];
    server.transcribe(sent.id, "two of them were mobbing the hawk");
    // No edit, nothing pending — the run that fetches it is the one that says
    // "Nothing to sync", which is exactly when this used to be skipped.
    await new SyncEngine(deps).syncAll();

    const stored = await deps.dictations.get("dct-1");
    expect(stored?.transcript).toBe("two of them were mobbing the hawk");
  });

  it("brings one back to a note on a merged-away part", async () => {
    // The pull used to start from list(), which hides a merge's parts — while
    // pushDictations reaches through them. A note could therefore go up from a
    // part and its transcript never come down: sent, transcribed, unreachable.
    const { server, deps } = harness();
    const partUuid = await capture(deps);
    await deps.dictations.add(note(partUuid));
    await new SyncEngine(deps).syncAll();
    const [sent] = [...server.dictations.values()];
    server.transcribe(sent.id, "seen off by the pair");

    const mergedUuid = await capture(deps);
    await deps.repository.update(mergedUuid, { mergedFrom: [partUuid] });
    await deps.repository.update(partUuid, { mergedInto: mergedUuid });

    await new SyncEngine(deps).syncAll();

    expect((await deps.dictations.get("dct-1"))?.transcript).toBe("seen off by the pair");
  });

  it("finds one pushed under the merge when the part never synced", async () => {
    // Pushed after the merge, the note lands under the merge's server capture,
    // because that is the id pushDictations had in hand. The pull has to look
    // there too — the part's own capture has no server row to ask.
    const { server, deps } = harness();
    const partUuid = await capture(deps);
    const mergedUuid = await capture(deps);
    await deps.dictations.add(note(partUuid));
    await deps.repository.update(mergedUuid, { mergedFrom: [partUuid] });
    await deps.repository.update(partUuid, { mergedInto: mergedUuid });

    await new SyncEngine(deps).syncAll();
    const [sent] = [...server.dictations.values()];
    server.transcribe(sent.id, "three juveniles begging");
    await new SyncEngine(deps).syncAll();

    expect((await deps.dictations.get("dct-1"))?.transcript).toBe("three juveniles begging");
  });

  it("counts what came down in the run's outcome", async () => {
    // "Nothing to sync" over a fetched transcript reads as the fetch never
    // happening. The outcome carries the count so the UI can say what the run
    // actually did.
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid));
    const first = await new SyncEngine(deps).syncAll();
    expect(first.transcripts).toBe(0);

    const [sent] = [...server.dictations.values()];
    server.transcribe(sent.id, "two of them were mobbing the hawk");
    const second = await new SyncEngine(deps).syncAll();
    expect(second.transcripts).toBe(1);
  });

  it("never registers a note as media", async () => {
    // The whole separation. A human voice track filed as bird audio is the
    // contamination the Keep flag exists to hold back.
    const { server, deps } = harness();
    const uuid = await capture(deps);
    await deps.dictations.add(note(uuid));

    await new SyncEngine(deps).syncAll();

    expect(server.mediaUuids()).not.toContain("dct-1");
  });
});
