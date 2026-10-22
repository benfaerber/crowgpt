import type { CaptureRepository } from "../data/CaptureRepository";
import type { NewCapture } from "../domain/types";
import type { FieldServerClient } from "../net/FieldServerClient";
import type { ServerCapture } from "../net/serverTypes";

/**
 * Pulling captures back down from the server.
 *
 * Sync is push-only by design: the phone is the source of truth and the server
 * never contradicts it. That rule is what keeps a field recording from being
 * silently overwritten by a stale copy, and it stays.
 *
 * Restore is the deliberate exception, because a phone that has *lost* a
 * capture has no truth to contradict. Capture 69 — a real field recording —
 * survived a reinstall only because it was on the server, and there was no way
 * to get it back onto the handset. The audio was safe and unreachable, which is
 * a strange place for a corpus to be.
 *
 * Only ever additive. A capture already on the phone is left completely alone,
 * including one mid-edit and one that has never synced. There is no merge here
 * and there should not be: the moment restore can overwrite, it can overwrite
 * the wrong way round.
 */

export interface Downloader {
  /**
   * Fetch a URL straight to a local file and return where it landed.
   *
   * A separate seam because a field recording is tens of megabytes: it must
   * stream to disk rather than through JS, and a fake can stand in for it in a
   * test without a filesystem.
   */
  download(url: string, headers: Record<string, string>, filename: string): Promise<{
    path: string;
    bytes: number;
  }>;
}

export interface RestoreOutcome {
  restored: string[];
  /** Already on the phone, so untouched. */
  skipped: number;
  /** Server-side captures with no complete audio to fetch. */
  unavailable: number;
  failed: { clientUuid: string; error: string }[];
}

/**
 * Restore is the one path where the server gets to hand the phone a value it
 * then writes to disk. `client_uuid` becomes both a filename (`${uuid}.wav`) and
 * the local capture key, and the File(dir, name) constructor does not reject
 * `..` — so a hostile or MITM'd server answering with
 * `client_uuid: "../SQLite/cawtalker.db"` steers the write at the phone's own
 * database, the source of truth in a push-only design. A real client_uuid is the
 * bare token the phone minted; anything with a path separator or traversal in it
 * was never ours to restore.
 */
const SAFE_UUID = /^[A-Za-z0-9_-]{1,64}$/;

export class Restore {
  constructor(
    private readonly repository: CaptureRepository,
    private readonly client: FieldServerClient,
    private readonly downloader: Downloader,
  ) {}

  async run(
    onProgress?: (done: number, total: number) => void,
  ): Promise<RestoreOutcome> {
    const outcome: RestoreOutcome = {
      restored: [], skipped: 0, unavailable: 0, failed: [],
    };
    const remote = await this.client.listCaptures();
    const local = new Set((await this.repository.list()).map((c) => c.uuid));

    let done = 0;
    for (const capture of remote) {
      done += 1;
      onProgress?.(done, remote.length);

      // Keyed on client_uuid, the same identity the push side is idempotent on.
      // A capture the server minted with no uuid was never ours to restore.
      const uuid = capture.client_uuid;
      if (!uuid) {
        outcome.unavailable += 1;
        continue;
      }
      if (!SAFE_UUID.test(uuid)) {
        // Not a uuid the phone could have minted, so not a capture to restore —
        // and the only way this string reaches a filesystem path is refused here.
        outcome.failed.push({ clientUuid: uuid, error: "unsafe client_uuid rejected" });
        continue;
      }
      if (local.has(uuid)) {
        outcome.skipped += 1;
        continue;
      }
      try {
        const added = await this.restoreOne(capture, uuid);
        if (added) outcome.restored.push(uuid);
        else outcome.unavailable += 1;
      } catch (failure) {
        // One capture failing must not end the run: the next one may be the
        // recording that mattered.
        outcome.failed.push({
          clientUuid: uuid,
          error: failure instanceof Error ? failure.message : String(failure),
        });
      }
    }
    return outcome;
  }

  private async restoreOne(capture: ServerCapture, uuid: string): Promise<boolean> {
    const media = await this.client.captureMedia(capture.id);
    const audio = media.find((m) => m.kind !== "video" && m.upload_state === "complete");
    if (!audio) return false;

    // Always a WAV, whatever the server stores. Everything this app does to
    // audio after it lands — the envelope, the playback boost, the crop —
    // reads RIFF headers directly, so a FLAC would arrive playable and inert.
    const { path, bytes } = await this.downloader.download(
      this.client.mediaUrl(audio.id, true),
      this.client.authHeadersFor(),
      `${uuid}.wav`,
    );

    // Every annotated field the phone sent, sent back. A capture restored
    // without them looks blank next to the one that was lost, and nothing says
    // it used to know more — which is the same silent-discard failure as a
    // newer phone pushing fields an older server drops, one direction round.
    //
    // TWO ARE LEFT OUT ON PURPOSE, and both would be bugs to add:
    //
    //   - the crop. The bytes above are ALREADY the cropped span — CroppedWav
    //     presents it as a whole file at upload time — so carrying
    //     crop_start_sec back would crop the crop, cutting a second bite out
    //     of a recording that has no original left on this phone to undo it
    //     against.
    //   - the family. `family_id` is a server id and a capture references its
    //     family by local uuid, so there is nothing honest to map it to until
    //     restore rebuilds families too. Better blank than pointed at whatever
    //     local family happens to hold that number.
    const record: NewCapture = {
      uuid,
      mediaUuid: audio.client_uuid ?? uuid,
      recordedAt: capture.recorded_at ?? new Date().toISOString(),
      durationMs: Math.round((capture.duration_sec ?? 0) * 1000),
      sampleRate: audio.sample_rate ?? 48000,
      channels: audio.channels ?? 1,
      audioPath: path,
      bytes,
      name: capture.name ?? undefined,
      keep: Boolean(capture.keep),
      latitude: capture.latitude ?? undefined,
      longitude: capture.longitude ?? undefined,
      locationName: capture.location_name ?? undefined,
      region: capture.region ?? undefined,
      notes: capture.notes ?? undefined,
      observerRole: capture.observer_role ?? undefined,
      behaviorGuess: capture.behavior_guess ?? undefined,
      silentConfirmedAt: capture.silent_confirmed_at ?? undefined,
      nothingToLabelAt: capture.nothing_to_label_at ?? undefined,
      distanceBand: capture.distance_band ?? undefined,
      adultCount: capture.adult_count ?? undefined,
      juvenileCount: capture.juvenile_count ?? undefined,
      unagedCount: capture.unaged_count ?? undefined,
      // The build that made the ORIGINAL recording, not the one restoring it.
      appVersion: capture.app_version ?? undefined,
      appCommit: capture.app_commit ?? undefined,
      trigger: capture.trigger === "auto" ? "auto" : undefined,
    };
    await this.repository.add(record);

    // Recorded as already delivered, and at the same revision it was fetched
    // at. Without this the phone would re-upload every restored capture and
    // then show them all as "Edited" — a restore that immediately looks like a
    // backlog of unsaved work.
    await this.repository.update(uuid, {
      serverCaptureId: capture.id,
      serverMediaId: audio.id,
      uploadedBytes: bytes,
      syncState: "synced",
      syncedAt: new Date().toISOString(),
      localRevision: 0,
      syncedRevision: 0,
    });
    return true;
  }
}
