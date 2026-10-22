import type { CaptureRepository } from "../data/CaptureRepository";
import type { FamilyRepository } from "../data/FamilyRepository";
import type { ContextRepository } from "../data/ContextRepository";
import type { SightingRepository } from "../data/SightingRepository";
import type { DictationRepository } from "../data/DictationRepository";
import { isPushable } from "../domain/dictations";
import type { LabelRepository } from "../data/LabelRepository";
import type { CaptureRecord } from "../domain/types";
import { coordsToSend, DEFAULT_FUZZ_MILES, type LocationPrecision } from "../domain/location";
import { needsDescriptionPush } from "../domain/revision";
import { isRetryable, isStaleServerLink } from "../net/HttpClient";
import type { FieldServerClient } from "../net/FieldServerClient";
import type { MediaSource } from "./MediaSource";
import { PullTranscripts } from "./PullTranscripts";
import { log } from "../app/Log";

export interface SyncProgress {
  captureUuid: string;
  /** 0..1 for the current capture's upload. */
  fraction: number;
  uploadedBytes: number;
  totalBytes: number;

  /** 1-based position of this capture in the run. */
  captureIndex: number;
  captureCount: number;
  /**
   * Run-level totals count only what this run actually has to send: a capture
   * resumed at 80% contributes its remaining 20%, not its whole size. Anything
   * else makes the bar jump on resume and the ETA a fiction.
   */
  bytesSent: number;
  bytesToSend: number;
  runFraction: number;
}

export interface SyncOutcome {
  synced: string[];
  failed: { uuid: string; error: string }[];
  /** True if the run stopped early because `cancel()` was called. */
  canceled: boolean;
  /**
   * Transcripts brought down this run. Counted so a run that pushed nothing
   * can still say what it did — "Nothing to sync" over a fetched transcript
   * reads as the fetch never happening, and was reported as exactly that.
   */
  transcripts: number;
}

/**
 * What one capture's upload reports upward. `sentThisCapture` counts only bytes
 * this run actually put on the wire, so a resumed capture doesn't credit the
 * run with the part that landed during an earlier one.
 */
interface CaptureProgress {
  forCapture: Omit<
    SyncProgress,
    "captureIndex" | "captureCount" | "bytesSent" | "bytesToSend" | "runFraction"
  >;
  sentThisCapture: number;
}

export interface SyncOptions {
  /** Bytes per PUT. Small enough that a dropped connection wastes little. */
  chunkBytes?: number;
  /** Ask the server to analyze each capture once its audio has landed. */
  requestAnalysis?: boolean;
  onProgress?: (progress: SyncProgress) => void;
}

/**
 * Raised when `cancel()` stops a capture mid-upload.
 *
 * Stopping has to be distinguishable from both success and failure. Returning
 * normally made a stopped capture count as synced *and* left it parked in
 * `syncing`, which `pendingSync` doesn't select — so it went quiet until the
 * next app start reset it. Treating it as a failure would be a lie of the
 * opposite kind: nothing went wrong, and it shouldn't burn a retry attempt.
 */
export class SyncCanceled extends Error {
  constructor() {
    super("sync stopped");
    this.name = "SyncCanceled";
  }
}

/**
 * Everything the engine pushes.
 *
 * One required object rather than six positional parameters, four of them
 * optional. The optional form let a caller build an engine that silently pushed
 * captures and nothing else — which is what happened: rebuilding the client
 * after a server change dropped `labels` and `context`, and labels stopped
 * syncing until the app was restarted, with nothing on screen to say so and
 * nothing in the compiler to object. Omitting one is now a type error.
 */
export interface SyncDeps {
  repository: CaptureRepository;
  /**
   * How precisely the recordist is willing to say where they were, read at
   * push time rather than at record time.
   *
   * A function rather than a value because it must be the *current* answer:
   * someone who tightens the setting expects the captures sitting in the queue
   * to stop carrying coordinates too, and an engine built at launch would still
   * be sending them.
   */
  locationPrecision: () => LocationPrecision;
  /**
   * The grid size `fuzzed` snaps to, in miles. Read at push time for the same
   * reason as the precision. Optional: only the fuzzed setting consults it.
   */
  fuzzMiles?: () => number;
  client: FieldServerClient;
  /** The audio as sync should see it — cropped, and merged where merged. */
  media: MediaSource;
  /**
   * The files exactly as they are on disk.
   *
   * For anything that is not a croppable WAV: an mp4, a spoken note. `media`
   * parses a RIFF header on every path it is given, so handing it either one
   * throws — which is what silently stopped every video capture from ever
   * uploading.
   */
  rawMedia: MediaSource;
  families: FamilyRepository;
  labels: LabelRepository;
  context: ContextRepository;
  sightings: SightingRepository;
  /** Spoken notes about a capture. Never bird audio. */
  dictations: DictationRepository;
}

/**
 * Pushes locally-stored captures to the field server, on demand.
 *
 * Nothing here runs on a timer or in the background: syncing happens when the
 * user asks for it, which is the whole point of recording local-first. That
 * makes interruption the normal case rather than the exceptional one, so every
 * step is written to be resumable and safe to repeat:
 *
 *   1. create the capture       — idempotent on `client_uuid`
 *   2. create the media slot    — idempotent on `client_uuid`; returns the
 *                                 server's byte count, which is where we resume
 *   3. PUT the remaining bytes  — ranged, chunk by chunk
 *   4. optionally request analysis
 *
 * Server ids and the confirmed byte offset are written back to the local store
 * as they are learned, so a sync that dies halfway resumes from the last
 * confirmed chunk rather than starting the file again.
 */
export class SyncEngine {
  private canceled = false;
  /**
   * Whether a run is in flight, kept here rather than in a screen.
   *
   * It used to be React state in `useCaptures`, which is mounted by the list
   * screen — so opening a capture mid-sync destroyed the only record that a
   * sync was happening. Coming back showed an idle bar over rows still marked
   * `syncing`, and pressing the button again started a *second* run over the
   * same captures.
   *
   * The engine is the only thing that knows, so the engine is where it lives.
   */
  private running = false;
  private readonly watchers = new Set<(running: boolean) => void>();
  private readonly repository: CaptureRepository;
  private readonly locationPrecision: () => LocationPrecision;
  private readonly fuzzMiles: () => number;
  private readonly client: FieldServerClient;
  private readonly media: MediaSource;
  private readonly rawMedia: MediaSource;
  private readonly dictations: DictationRepository;
  private readonly families: FamilyRepository;
  private readonly labels: LabelRepository;
  private readonly context: ContextRepository;
  private readonly sightings: SightingRepository;

  constructor(deps: SyncDeps) {
    this.repository = deps.repository;
    this.locationPrecision = deps.locationPrecision;
    this.fuzzMiles = deps.fuzzMiles ?? (() => DEFAULT_FUZZ_MILES);
    this.client = deps.client;
    this.media = deps.media;
    this.rawMedia = deps.rawMedia;
    this.dictations = deps.dictations;
    this.families = deps.families;
    this.labels = deps.labels;
    this.context = deps.context;
    this.sightings = deps.sightings;
  }

  /**
   * Push families first.
   *
   * A capture carries a family by *local* uuid, but the server wants its own id,
   * so the family has to exist up there before any capture referencing it is
   * created — otherwise the capture lands unattached and the grouping is lost
   * with no error to notice.
   */
  private async syncFamilies(): Promise<void> {
    for (const family of await this.families.pendingSync()) {
      const created = await this.client.createFamily({
        clientUuid: family.uuid,
        name: family.name,
        color: family.color,
        notes: family.notes,
      });
      await this.families.update(family.uuid, {
        serverId: created.id,
        syncedAt: new Date().toISOString(),
      });
    }
  }

  /**
   * Tell the server which captures this one replaced, once its audio is up.
   *
   * After the bytes, deliberately: the record says "these are superseded by
   * that", and pointing at a capture the server cannot yet play would be a
   * claim it has no way to check.
   *
   * Only parts that reached the server are named. One that never synced was
   * folded in locally and is inside the joined audio, so there is nothing up
   * there to supersede — and when none of them synced there is nothing to send
   * at all, which is the ordinary case for a merge made before the first sync.
   *
   * A failure here is logged, not thrown. The audio is already safe; retrying
   * the whole capture to re-send a record the server may already hold would
   * risk the upload to protect the bookkeeping.
   */
  private async pushMerge(capture: CaptureRecord): Promise<void> {
    if (!capture.mergedFrom || capture.mergedFrom.length === 0) return;

    const parts: { captureId: number; offsetMs: number }[] = [];
    const offsets = await this.mergeOffsets(capture);
    for (const uuid of capture.mergedFrom) {
      const part = await this.repository.get(uuid);
      if (!part?.serverCaptureId) continue;
      parts.push({
        captureId: part.serverCaptureId,
        offsetMs: offsets.get(uuid) ?? 0,
      });
    }
    if (parts.length === 0) return;

    try {
      await this.client.recordMerge(capture.serverCaptureId!, parts);
    } catch (failure) {
      log.error("sync", "merge record was refused", failure);
    }
  }

  /** Where each part sits in the joined audio, measured from the audio itself. */
  private async mergeOffsets(capture: CaptureRecord): Promise<Map<string, number>> {
    const offsets = new Map<string, number>();
    const source = this.media as { offsets?: (path: string) => Promise<
      { uuid: string; offsetMs: number }[]> };
    if (typeof source.offsets !== "function") return offsets;
    try {
      for (const placed of await source.offsets(capture.audioPath)) {
        offsets.set(placed.uuid, placed.offsetMs);
      }
    } catch (failure) {
      // Falling back to zeroes would put every rebased label at the start of
      // the recording, which is worse than having no record at all.
      log.error("sync", "could not read merge offsets", failure);
      throw failure;
    }
    return offsets;
  }

  /**
   * Send every spoken note this capture is carrying.
   *
   * Failures are logged and swallowed, as `pushMerge` does: the recording has
   * already landed by the time this runs, and failing the whole capture to
   * retry a note would risk re-sending megabytes of audio to protect a memo.
   */
  private async pushDictations(capture: CaptureRecord, chunkBytes: number): Promise<void> {
    // The merge's own uuid AND its parts'. `isPendingSync` returns false for
    // anything with `mergedInto`, so a note recorded against a take that later
    // became part of a bout would otherwise be stranded on the phone forever
    // with nothing anywhere saying so.
    const owners = [capture.uuid, ...(capture.mergedFrom ?? [])];
    const notes = (await this.dictations.forCaptures(owners)).filter(isPushable);
    for (const note of notes) {
      if (this.canceled) throw new SyncCanceled();
      try {
        const slot = await this.client.createDictation(capture.serverCaptureId!, {
          clientUuid: note.uuid,
          recordedAt: note.recordedAt,
          durationSec: note.durationMs / 1000,
          sampleRate: note.sampleRate,
          channels: note.channels,
          format: "wav",
        });
        await this.dictations.update(note.uuid, {
          serverId: slot.id, uploadedBytes: slot.bytes,
        });
        // The row's own byte count, never the file's size on disk: a note the
        // app died during has a real file and a meaningless length, and
        // `isPushable` has already decided this one is worth sending.
        const total = note.bytes;
        let offset = slot.bytes;
        while (offset < total) {
          if (this.canceled) throw new SyncCanceled();
          const chunk = await this.rawMedia.read(note.audioPath, offset, chunkBytes);
          if (chunk.byteLength === 0) break;
          const updated = await this.client.uploadDictationChunk(
            slot.id, chunk, offset, total);
          // Same rule as the audio: only `upload_state` is a statement about
          // progress, because the server's `bytes` can move underneath it.
          offset = updated.upload_state === "complete" ? total : updated.bytes;
          await this.dictations.update(note.uuid, { uploadedBytes: offset });
        }
        await this.dictations.update(note.uuid, {
          syncedAt: new Date().toISOString(),
        });
      } catch (failure) {
        if (failure instanceof SyncCanceled) throw failure;
        log.error("sync", "a spoken note was refused", failure, {
          dictation: note.uuid, capture: capture.uuid,
        });
      }
    }
  }

  /**
   * Send this capture's field labels.
   *
   * A failure here is not a failed sync: the audio is what matters most and it
   * has already landed. The labels stay pending and go up on the next run,
   * which is exactly what their idempotency key is for.
   */
  private async pushLabels(captureUuid: string, serverCaptureId: number): Promise<void> {
    const pending = (await this.labels.forCapture(captureUuid)).filter(
      (label) => label.serverId === undefined,
    );
    for (const label of pending) {
      const created = await this.client.addLabel(serverCaptureId, {
        clientUuid: label.uuid,
        callType: label.callType,
        species: label.species,
        startSec: label.startSec,
        endSec: label.endSec,
        // From the label, not from the phone's current config: this may be
        // pushing something decided last week under a vocabulary since replaced.
        configVersion: label.configVersion,
        // Seen, or absent. The one field here that cannot be recovered if it
        // never makes the trip — see LabelRecord.callerRole.
        callerRole: label.callerRole,
      });
      await this.labels.update(label.uuid, {
        serverId: created.id,
        syncedAt: new Date().toISOString(),
      });
    }
  }

  /**
   * Send out-of-frame sightings.
   *
   * Independent of the labels, unlike context — a sighting is about the
   * recording as a whole, not about one call in it, so nothing has to have
   * landed first.
   */
  private async pushSightings(captureUuid: string, serverCaptureId: number): Promise<void> {
    const pending = (await this.sightings.forCapture(captureUuid)).filter(
      (sighting) => sighting.serverId === undefined,
    );
    for (const sighting of pending) {
      const created = await this.client.addSighting(serverCaptureId, {
        clientUuid: sighting.uuid,
        key: sighting.key,
        offsetSec: sighting.offsetSec,
        distanceM: sighting.distanceM,
        notes: sighting.notes,
      });
      await this.sightings.update(sighting.uuid, {
        serverId: created.id,
        syncedAt: new Date().toISOString(),
      });
    }
  }

  /**
   * Send what the recordist witnessed.
   *
   * Strictly after the labels, because each event names the call it was the
   * situation for and the server wants that call's id. An event whose label has
   * not landed yet is skipped rather than dropped — it goes on the next run,
   * which is what its idempotency key is for.
   */
  private async pushContext(captureUuid: string, serverCaptureId: number): Promise<void> {
    const labels = await this.labels.forCapture(captureUuid);
    const pending = (await this.context.forCapture(captureUuid)).filter(
      (event) => event.serverId === undefined,
    );
    for (const event of pending) {
      // A capture-level event — only legal on a confirmed-silent recording —
      // has no label, so there is nothing to wait for. Events that *name* a
      // label still wait for it to land, or they would arrive unattached.
      const captureLevel = !event.labelUuid;
      const labelId = captureLevel
        ? undefined
        : labels.find((l) => l.uuid === event.labelUuid)?.serverId;
      if (!captureLevel && labelId === undefined) continue;
      const created = await this.client.addContext(serverCaptureId, {
        clientUuid: event.uuid,
        labelId,
        key: event.key,
        startSec: event.startSec,
        endSec: event.endSec,
        notes: event.notes,
        configVersion: event.configVersion,
      });
      await this.context.update(event.uuid, {
        serverId: created.id,
        syncedAt: new Date().toISOString(),
      });
    }
  }

  /** Ask an in-flight `syncAll` to stop after the current chunk. */
  cancel(): void {
    this.canceled = true;
  }

  get isRunning(): boolean {
    return this.running;
  }

  /** Watch the run state. Returns the unsubscribe. */
  onRunningChanged(watcher: (running: boolean) => void): () => void {
    this.watchers.add(watcher);
    return () => {
      this.watchers.delete(watcher);
    };
  }

  private setRunning(running: boolean): void {
    if (this.running === running) return;
    this.running = running;
    for (const watcher of this.watchers) watcher(running);
  }

  async syncAll(options: SyncOptions = {}): Promise<SyncOutcome> {
    // One run at a time, whoever asks. Two concurrent runs would upload the
    // same captures twice — idempotency saves the corpus from that, but not the
    // bandwidth, and not a progress bar driven by both at once.
    if (this.running) return { synced: [], failed: [], canceled: true, transcripts: 0 };
    this.setRunning(true);
    try {
      return await this.run(options);
    } finally {
      this.setRunning(false);
    }
  }

  private async run(options: SyncOptions): Promise<SyncOutcome> {
    this.canceled = false;
    const outcome: SyncOutcome = { synced: [], failed: [], canceled: false, transcripts: 0 };
    await this.syncFamilies();
    const pending = await this.repository.pendingSync();

    // Spoken notes count towards the total. Without them a capture that has
    // already synced but is carrying a new note reports 0 of 0 while megabytes
    // go up — which is what a bar reaching 100% before the work starts looks
    // like from outside, and it was reported as exactly that.
    const notesPending = await this.dictations.pendingSync();
    const notesByCapture = new Map<string, number>();
    for (const note of notesPending) {
      if (!isPushable(note)) continue;
      notesByCapture.set(
        note.captureUuid,
        (notesByCapture.get(note.captureUuid) ?? 0)
          + Math.max(0, note.bytes - note.uploadedBytes));
    }
    const notesFor = (capture: CaptureRecord) =>
      [capture.uuid, ...(capture.mergedFrom ?? [])]
        .reduce((total, uuid) => total + (notesByCapture.get(uuid) ?? 0), 0);

    const bytesToSend = pending.reduce((total, capture) => {
      const audio = Math.max(0, capture.bytes - capture.uploadedBytes);
      const video = capture.videoPath
        ? Math.max(0, (capture.videoBytes ?? 0) - (capture.videoUploadedBytes ?? 0))
        : 0;
      return total + audio + video + notesFor(capture);
    }, 0);
    let bytesSent = 0;
    let index = 0;

    for (const capture of pending) {
      if (this.canceled) {
        outcome.canceled = true;
        break;
      }
      index += 1;
      const startedAt = bytesSent;
      const relay = options.onProgress
        ? (progress: CaptureProgress) => {
            bytesSent = startedAt + progress.sentThisCapture;
            options.onProgress?.({
              ...progress.forCapture,
              captureIndex: index,
              captureCount: pending.length,
              bytesSent,
              bytesToSend,
              runFraction: bytesToSend > 0 ? Math.min(1, bytesSent / bytesToSend) : 1,
            });
          }
        : undefined;
      try {
        await this.syncOne(capture, options, relay);
        outcome.synced.push(capture.uuid);
        // Whatever the per-chunk reports missed, the capture is done now.
        bytesSent =
          startedAt +
          Math.max(0, capture.bytes - capture.uploadedBytes) +
          (capture.videoPath
            ? Math.max(0, (capture.videoBytes ?? 0) - (capture.videoUploadedBytes ?? 0))
            : 0) +
          notesFor(capture);
      } catch (error) {
        if (error instanceof SyncCanceled) {
          // Put it back in the queue rather than leaving it parked in
          // `syncing`. The bytes the server confirmed are already recorded, so
          // the next run resumes from there instead of re-sending them.
          await this.repository.update(capture.uuid, {
            syncState: "local",
            lastError: undefined,
          });
          outcome.canceled = true;
          break;
        }
        const message = error instanceof Error ? error.message : String(error);
        // Retryable or not, the row records the same thing: failed, with the
        // reason. A 4xx will fail identically next time, but the next run is
        // the user's call and `lastError` is what tells them which it was.
        await this.repository.update(capture.uuid, {
          syncState: "failed",
          lastError: message,
          attempts: capture.attempts + 1,
        });
        outcome.failed.push({ uuid: capture.uuid, error: message });
      }
    }
    // After the pushing, and unconditionally: a run with nothing to send is
    // exactly when a transcript made since the last one is waiting.
    // The exception to push-only lives in its own file; see PullTranscripts.
    outcome.transcripts = await new PullTranscripts(
      this.repository, this.dictations, this.client,
    ).run();
    return outcome;
  }

  /**
   * Sync one capture, healing a stale server link if we hit one.
   *
   * A remembered `serverCaptureId` can outlive the identity that created it —
   * re-enrolling gives the device a new identity, and the server then rightly
   * answers "not your capture" for rows the old one made. Left alone that
   * capture is stuck failing forever, so drop the dead ids and let the normal
   * idempotent create mint fresh ones under the current identity.
   */
  async syncOne(
    capture: CaptureRecord,
    options: SyncOptions = {},
    relay?: (progress: CaptureProgress) => void,
  ): Promise<CaptureRecord> {
    try {
      return await this.attempt(capture, options, relay);
    } catch (error) {
      if (!isStaleServerLink(error) || capture.serverCaptureId === undefined) throw error;
      const reset = await this.repository.update(capture.uuid, {
        serverCaptureId: undefined,
        serverMediaId: undefined,
        uploadedBytes: 0,
      });
      return this.attempt(reset, options, relay);
    }
  }

  private async attempt(
    capture: CaptureRecord,
    options: SyncOptions,
    relay?: (progress: CaptureProgress) => void,
  ): Promise<CaptureRecord> {
    const chunkBytes = options.chunkBytes ?? 256 * 1024;
    const revisionAtStart = capture.localRevision ?? 0;
    let current = await this.repository.update(capture.uuid, {
      syncState: "syncing",
      lastError: undefined,
    });

    const family = current.familyUuid
      ? await this.families.get(current.familyUuid)
      : undefined;

    if (current.serverCaptureId === undefined) {
      const created = await this.client.createCapture({
        clientUuid: current.uuid,
        name: current.name,
        keep: current.keep,
        familyId: family?.serverId,
        // The single gate on coordinates leaving this phone. Not a filter at
        // record time, because the answer may have changed since — and not a
        // rule the server applies, because a promise the phone keeps is a fact
        // and one the server keeps is a promise.
        ...coordsToSend(current, this.locationPrecision(), this.fuzzMiles()),
        // Says how coarse the coordinates above are, so a snapped fix can
        // never be mistaken for an exact one downstream.
        coordFuzzMiles:
          this.locationPrecision() === "fuzzed" ? this.fuzzMiles() : undefined,
        region: current.region,
        locationName: current.locationName,
        recordedAt: current.recordedAt,
        durationSec: current.durationMs / 1000,
        notes: current.notes,
        appVersion: current.appVersion,
        appCommit: current.appCommit,
        // Create-only, like the app version: how a recording started is a
        // fact about the recording, not an edit anybody makes later.
        trigger: current.trigger,
        observerRole: current.observerRole,
        behaviorGuess: current.behaviorGuess,
        // Deliberately not in SYNCED_FIELDS: re-cropping after the audio has
        // landed would move these without moving the bytes, and metadata that
        // disagrees with the file is worse than metadata that is missing.
        cropStartSec: current.cropStartSec,
        cropEndSec: current.cropEndSec,
        distanceBand: current.distanceBand,
        adultCount: current.adultCount,
        juvenileCount: current.juvenileCount,
        unagedCount: current.unagedCount,
      });
      current = await this.repository.update(current.uuid, { serverCaptureId: created.id });
    } else if (revisionAtStart > (current.syncedRevision ?? 0)) {
      // The capture is already on the server, so `createCapture` above won't
      // run — and it is the only place these fields were ever sent. Without
      // this, tagging a family after the upload re-synced forever and silently
      // never landed, while the revision bookkeeping declared it delivered.
      await this.client.updateCapture(current.serverCaptureId, {
        name: current.name,
        keep: current.keep,
        familyId: family?.serverId,
        ...coordsToSend(current, this.locationPrecision(), this.fuzzMiles()),
        coordFuzzMiles:
          this.locationPrecision() === "fuzzed" ? this.fuzzMiles() : undefined,
        region: current.region,
        locationName: current.locationName,
        notes: current.notes,
        observerRole: current.observerRole,
        behaviorGuess: current.behaviorGuess,
        distanceBand: current.distanceBand,
        adultCount: current.adultCount,
        juvenileCount: current.juvenileCount,
        unagedCount: current.unagedCount,
        // Sent as a boolean, not the timestamp: the server stamps its own when
        // it accepts the claim, and two clocks writing one field is how a phone
        // that is a minute behind starts unmarking things.
        silent: current.silentConfirmedAt !== undefined,
        // Same shape and the same reason: the server stamps the clock it
        // trusts rather than taking a phone's.
        nothingToLabel: current.nothingToLabelAt !== undefined,
      });
    }

    const slot = await this.client.createMedia(current.serverCaptureId!, {
      clientUuid: current.mediaUuid,
      sampleRate: current.sampleRate,
      channels: current.channels,
      // Only on the audio slot: the camera records muted, so the video row has
      // no microphone of its own to describe.
      inputDevice: current.inputDevice,
      inputHonoured: current.inputHonoured,
      preRollSec: current.preRollSec,
    });
    const total = await this.media.size(current.audioPath);
    // The server's count wins: it is the only party that knows what actually
    // landed, and a local guess can be ahead of reality after a dropped request.
    //
    // But `bytes` only measures progress while the upload is still open. The
    // same rule the chunk loop below spells out applies to the slot itself:
    // once it is complete the server has compressed the WAV to FLAC, and the
    // size it reports from then on is the stored file's, not an offset into
    // anything this phone holds. Adopting it re-opened a finished upload at
    // roughly a quarter of the way in, and the server — which seals a complete
    // upload so one operator cannot overwrite another's recording — refused
    // every chunk with a 400. Capture 153, "Fledgling annoys his dad", failed
    // on every sync for a day after its audio was safely on the server, and
    // because `pendingSync` re-selects a failed row it would have failed
    // forever.
    current = await this.repository.update(current.uuid, {
      serverMediaId: slot.id,
      uploadedBytes: slot.upload_state === "complete" ? total : slot.bytes,
    });

    let offset = current.uploadedBytes;
    const startedFrom = offset;

    const report = (at: number) =>
      relay?.({
        forCapture: {
          captureUuid: current.uuid,
          fraction: total === 0 ? 1 : at / total,
          uploadedBytes: at,
          totalBytes: total,
        },
        sentThisCapture: Math.max(0, at - startedFrom),
      });

    // Run-level progress has to count the video too, or a capture with one
    // shows the bar finishing while tens of megabytes are still going up.
    const videoAlready = capture.videoUploadedBytes ?? 0;
    const reportVideo = (at: number, total: number) =>
      relay?.({
        forCapture: {
          captureUuid: current.uuid,
          fraction: total === 0 ? 1 : at / total,
          uploadedBytes: at,
          totalBytes: total,
        },
        sentThisCapture: Math.max(0, offset - startedFrom) + Math.max(0, at - videoAlready),
      });

    report(offset);

    while (offset < total) {
      if (this.canceled) throw new SyncCanceled();
      const chunk = await this.media.read(current.audioPath, offset, chunkBytes);
      if (chunk.byteLength === 0) break;
      const updated = await this.client.uploadChunk(current.serverMediaId!, chunk, offset, total);
      // The server says when it is done; `bytes` cannot.
      //
      // finalize() compresses the assembled WAV to FLAC and answers with the
      // row *afterwards*, so the response to the last chunk carries the FLAC
      // size — well under the total declared. Taking that as the new offset
      // said "you are at 22% of the file, go round again", and the next PUT
      // wrote into a finished FLAC at an offset that means nothing in it.
      // Confirmed as arithmetic against a temp instance: 16044 bytes in,
      // 11829 back, loop condition still true.
      offset = updated.upload_state === "complete" ? total : updated.bytes;
      current = await this.repository.update(current.uuid, { uploadedBytes: offset });
      report(offset);
    }

    // Video after audio, deliberately. The audio is what the model needs and
    // what analysis waits on; video is context and is far larger, so a sync cut
    // short over a bad link should already have delivered the part that matters.
    // Between the audio and the video, deliberately. The audio is the recording
    // and goes first; a spoken note is small and is the labelling bottleneck;
    // the video is bulky context and can wait for the end of a good link.
    await this.pushDictations(current, chunkBytes);

    if (current.videoPath && current.videoMediaUuid) {
      // Bound once: `current` is reassigned on every write below, which loses
      // the narrowing these two just earned.
      const videoPath = current.videoPath;
      const videoSlot = await this.client.createMedia(current.serverCaptureId!, {
        clientUuid: current.videoMediaUuid,
        kind: "video",
        format: "mp4",
      });
      // rawMedia, NOT media. `this.media` is MergedWavSource(CroppedWavSource(…)),
      // built to present the AUDIO as a cropped view — and CroppedWavSource
      // parses a RIFF header on every path it is handed, whether or not a crop
      // exists. So this line used to feed an mp4 into a WAV parser and throw
      // "not a RIFF/WAVE file", on every sync, forever: every video capture ever
      // made sat at "On phone" while its audio half uploaded fine. A crop is a
      // span of PCM and means nothing to an mp4; a video must never go through
      // that wrapper.
      const videoTotal = await this.rawMedia.size(videoPath);
      // Same rule as the audio slot: a complete upload is sealed, and its
      // reported size stops being an offset the moment it finishes.
      current = await this.repository.update(current.uuid, {
        videoServerMediaId: videoSlot.id,
        videoUploadedBytes:
          videoSlot.upload_state === "complete" ? videoTotal : videoSlot.bytes,
      });

      let videoOffset = current.videoUploadedBytes ?? 0;
      while (videoOffset < videoTotal) {
        if (this.canceled) throw new SyncCanceled();
        const chunk = await this.rawMedia.read(videoPath, videoOffset, chunkBytes);
        if (chunk.byteLength === 0) break;
        const updated = await this.client.uploadChunk(
          current.videoServerMediaId!, chunk, videoOffset, videoTotal,
        );
        // Same rule as the audio above: compression moves `bytes` underneath
        // the arithmetic, and only upload_state is a statement about progress.
        videoOffset = updated.upload_state === "complete" ? videoTotal : updated.bytes;
        current = await this.repository.update(current.uuid, {
          videoUploadedBytes: videoOffset,
        });
        reportVideo(videoOffset, videoTotal);
      }
    }

    // The description goes up after the audio, so a note never arrives
    // attached to a capture whose recording failed to land.
    if (needsDescriptionPush(current)) {
      await this.client.addObservation(current.serverCaptureId!, {
        clientUuid: current.descriptionUuid!,
        body: current.description!.trim(),
      });
      current = await this.repository.update(current.uuid, {
        descriptionSyncedAt: new Date().toISOString(),
        descriptionSyncedBody: current.description!.trim(),
      });
    }

    // Labels last: each one names a span of the audio, so pushing before the
    // bytes have landed would attach ground truth to a recording the server
    // cannot yet play. Idempotent on their own uuid, so a retry is free.
    await this.pushLabels(current.uuid, current.serverCaptureId!);
    await this.pushContext(current.uuid, current.serverCaptureId!);
    await this.pushSightings(current.uuid, current.serverCaptureId!);
    await this.pushMerge(current);

    // Only for audio the server has not analyzed yet. Re-pushing a capture
    // because its description changed must not re-run inference on a recording
    // that has not changed — that is minutes of worker time for a typo fix.
    const audioIsNew = startedFrom < total || capture.syncState !== "synced";
    if (options.requestAnalysis && audioIsNew) {
      await this.client.requestAnalysis(current.serverCaptureId!);
    }

    return this.repository.update(current.uuid, {
      syncState: "synced",
      syncedAt: new Date().toISOString(),
      // The revision as it was when this push *started*. An edit made while the
      // upload was in flight is not in what was sent, so it has to stay owed —
      // marking it clean here would strand it exactly the way a post-sync
      // description used to be stranded. Worst case is one redundant re-push,
      // which is idempotent and cheap.
      syncedRevision: revisionAtStart,
      lastError: undefined,
    });
  }
}
