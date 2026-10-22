import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import { CaptureNotFound, type CaptureRepository } from "./CaptureRepository";
import { isDirtyingChange } from "../domain/revision";
import type { CaptureRecord, NewCapture, SyncState } from "../domain/types";

type Row = {
  uuid: string;
  media_uuid: string;
  name: string | null;
  recorded_at: string;
  duration_ms: number;
  sample_rate: number;
  channels: number;
  audio_path: string;
  bytes: number;
  video_path: string | null;
  video_bytes: number | null;
  video_media_uuid: string | null;
  video_server_media_id: number | null;
  video_uploaded_bytes: number | null;
  envelope_json: string | null;
  crop_start_sec: number | null;
  crop_end_sec: number | null;
  keep: number | null;
  family_uuid: string | null;
  latitude: number | null;
  longitude: number | null;
  location_name: string | null;
  region: string | null;
  notes: string | null;
  description: string | null;
  description_uuid: string | null;
  description_updated_at: string | null;
  description_synced_at: string | null;
  description_synced_body: string | null;
  sync_state: SyncState;
  server_capture_id: number | null;
  server_media_id: number | null;
  uploaded_bytes: number;
  synced_at: string | null;
  attempts: number;
  last_error: string | null;
  local_revision: number | null;
  synced_revision: number | null;
  input_device: string | null;
  input_honoured: number | null;
  pre_roll_sec: number | null;
  app_version: number | null;
  app_commit: string | null;
  trigger: string | null;
  observer_role: string | null;
  distance_band: string | null;
  adult_count: number | null;
  juvenile_count: number | null;
  unaged_count: number | null;
  silent_confirmed_at: string | null;
  nothing_to_label_at: string | null;
  behavior_guess: string | null;
  merged_from: string | null;
  merged_into: string | null;
};

/**
 * The real local store.
 *
 * This is what makes the app local-first rather than merely offline-tolerant: a
 * capture survives the process dying, the phone rebooting, and a week in a bag
 * with no signal. Sync bookkeeping lives in the same row as the capture, so
 * there is no second place where a half-finished upload could be remembered
 * inconsistently.
 */
export class SqliteCaptureRepository implements CaptureRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteCaptureRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS captures (
        uuid TEXT PRIMARY KEY NOT NULL,
        media_uuid TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL,
        sample_rate INTEGER NOT NULL,
        channels INTEGER NOT NULL,
        audio_path TEXT NOT NULL,
        bytes INTEGER NOT NULL,
        video_path TEXT,
        video_bytes INTEGER,
        video_media_uuid TEXT,
        video_server_media_id INTEGER,
        video_uploaded_bytes INTEGER,
        envelope_json TEXT,
        crop_start_sec REAL,
        crop_end_sec REAL,
        keep INTEGER NOT NULL DEFAULT 0,
        family_uuid TEXT,
        latitude REAL,
        longitude REAL,
        location_name TEXT,
        region TEXT,
        notes TEXT,
        description TEXT,
        description_uuid TEXT,
        description_updated_at TEXT,
        description_synced_at TEXT,
        description_synced_body TEXT,
        sync_state TEXT NOT NULL DEFAULT 'local',
        server_capture_id INTEGER,
        server_media_id INTEGER,
        uploaded_bytes INTEGER NOT NULL DEFAULT 0,
        synced_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
      );
      CREATE INDEX IF NOT EXISTS captures_sync_state ON captures (sync_state);
    `);
    // Existing installs predate the description columns; add them in place
    // rather than making anyone reinstall and lose their captures.
    for (const [column, decl] of [
      ["description", "TEXT"],
      ["description_uuid", "TEXT"],
      ["description_updated_at", "TEXT"],
      ["description_synced_at", "TEXT"],
      ["description_synced_body", "TEXT"],
      ["video_path", "TEXT"],
      ["video_bytes", "INTEGER"],
      ["video_media_uuid", "TEXT"],
      ["video_server_media_id", "INTEGER"],
      ["video_uploaded_bytes", "INTEGER"],
      ["envelope_json", "TEXT"],
      ["crop_start_sec", "REAL"],
      ["crop_end_sec", "REAL"],
      ["keep", "INTEGER NOT NULL DEFAULT 0"],
      ["family_uuid", "TEXT"],
      // Existing captures start level: whatever is already on the server is
      // treated as current, so adding this doesn't queue the entire library for
      // a re-push the first time the app opens.
      ["local_revision", "INTEGER NOT NULL DEFAULT 0"],
      ["synced_revision", "INTEGER NOT NULL DEFAULT 0"],
      // Null on everything recorded before mic pinning existed, which is the
      // honest answer for those: nobody knows which mic they used.
      ["input_device", "TEXT"],
      ["input_honoured", "INTEGER"],
      // Null on everything recorded before the rolling buffer existed. Not the
      // same as 0, which asserts the recording really did start at the press.
      ["pre_roll_sec", "REAL"],
      // Null on everything recorded before the app stamped itself. Honest: the
      // build that made those is genuinely unknown now.
      ["app_version", "INTEGER"],
      ["app_commit", "TEXT"],
      // "auto" when the idle trigger started the recording. Null on
      // everything else, including every capture from before the trigger
      // existed — those were all a person pressing a button.
      ["trigger", "TEXT"],
      ["observer_role", "TEXT"],
      ["distance_band", "TEXT"],
      ["adult_count", "INTEGER"],
      ["juvenile_count", "INTEGER"],
      ["unaged_count", "INTEGER"],
      ["silent_confirmed_at", "TEXT"],
      ["nothing_to_label_at", "TEXT"],
      ["behavior_guess", "TEXT"],
      // The parts a merged capture was joined from, in play order, and the
      // capture a part was folded into. A part keeps its row and its audio —
      // it stops being listed, which is what "the originals go away" means.
      ["merged_from", "TEXT"],
      ["merged_into", "TEXT"],
      ["name", "TEXT"],
    ] as const) {
      const existing = await db.getAllAsync<{ name: string }>("PRAGMA table_info(captures)");
      if (!existing.some((row) => row.name === column)) {
        await db.execAsync(`ALTER TABLE captures ADD COLUMN ${column} ${decl}`);
      }
    }

    const store = new SqliteCaptureRepository(db);
    // A capture left mid-flight by a crash is not actually in flight any more.
    await store.recoverInterrupted();
    return store;
  }

  /**
   * Insert the NOT NULL columns, then let `update` write everything else.
   *
   * Deliberately not one big INSERT listing every column: this class used to
   * enumerate columns here *and* in `update`, and the two drifted — video fields
   * were added to the schema, the row type, the column map and the mapper, but
   * not to the INSERT, so a filmed capture silently lost its video the instant
   * it was saved. One list, used by both paths, cannot drift.
   */
  async add(capture: NewCapture): Promise<CaptureRecord> {
    await this.db.runAsync(
      `INSERT INTO captures (uuid, media_uuid, recorded_at, duration_ms, sample_rate,
                             channels, audio_path, bytes, sync_state, uploaded_bytes, attempts)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', 0, 0)`,
      [
        capture.uuid,
        capture.mediaUuid,
        capture.recordedAt,
        capture.durationMs,
        capture.sampleRate,
        capture.channels,
        capture.audioPath,
        capture.bytes,
      ],
    );
    return this.update(capture.uuid, capture);
  }

  async get(uuid: string): Promise<CaptureRecord | null> {
    const row = await this.db.getFirstAsync<Row>("SELECT * FROM captures WHERE uuid = ?", [uuid]);
    return row ? this.toRecord(row) : null;
  }

  async list(): Promise<CaptureRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      // Parts of a merge are excluded rather than deleted. "The originals go
      // away" is a statement about this list; the recordings survive, which is
      // what makes a merge undoable.
      "SELECT * FROM captures WHERE merged_into IS NULL ORDER BY recorded_at DESC",
    );
    return rows.map((row) => this.toRecord(row));
  }

  /** Merge parts included on purpose — see the interface. */
  async audioPaths(): Promise<string[]> {
    const rows = await this.db.getAllAsync<{ audio_path: string | null }>(
      "SELECT audio_path FROM captures",
    );
    return rows.map((row) => row.audio_path).filter((path): path is string => !!path);
  }

  /**
   * Everything that owes the server something — never sent, failed, or edited
   * since it last synced.
   *
   * The last clause is why a description typed after the upload now arrives: a
   * synced capture used to be excluded forever, so there was no way to ask for
   * the change to be sent.
   */
  async pendingSync(): Promise<CaptureRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      // A part is never pushed on its own — the merge is pushed instead, and it
      // carries every part's samples, so nothing is lost by not sending them
      // twice. One that had already synced before the merge stays on the server
      // and is accounted for by the merge record; one that had not simply
      // travels inside the joined audio.
      `SELECT * FROM captures
        WHERE merged_into IS NULL
          AND (sync_state IN ('local', 'failed')
               OR (sync_state = 'synced' AND local_revision > synced_revision))
        ORDER BY recorded_at ASC`,
    );
    return rows.map((row) => this.toRecord(row));
  }

  async update(uuid: string, patch: Partial<CaptureRecord>): Promise<CaptureRecord> {
    const columns: Record<keyof CaptureRecord, string> = {
      uuid: "uuid",
      mediaUuid: "media_uuid",
      name: "name",
      recordedAt: "recorded_at",
      durationMs: "duration_ms",
      sampleRate: "sample_rate",
      channels: "channels",
      audioPath: "audio_path",
      bytes: "bytes",
      videoPath: "video_path",
      videoBytes: "video_bytes",
      videoMediaUuid: "video_media_uuid",
      videoServerMediaId: "video_server_media_id",
      videoUploadedBytes: "video_uploaded_bytes",
      inputDevice: "input_device",
      inputHonoured: "input_honoured",
      preRollSec: "pre_roll_sec",
      appVersion: "app_version",
      appCommit: "app_commit",
      trigger: "trigger",
      observerRole: "observer_role",
      distanceBand: "distance_band",
      adultCount: "adult_count",
      juvenileCount: "juvenile_count",
      unagedCount: "unaged_count",
      silentConfirmedAt: "silent_confirmed_at",
      nothingToLabelAt: "nothing_to_label_at",
      behaviorGuess: "behavior_guess",
      mergedFrom: "merged_from",
      mergedInto: "merged_into",
      envelopeJson: "envelope_json",
      cropStartSec: "crop_start_sec",
      cropEndSec: "crop_end_sec",
      keep: "keep",
      familyUuid: "family_uuid",
      latitude: "latitude",
      longitude: "longitude",
      locationName: "location_name",
      region: "region",
      notes: "notes",
      description: "description",
      descriptionUuid: "description_uuid",
      descriptionUpdatedAt: "description_updated_at",
      descriptionSyncedAt: "description_synced_at",
      descriptionSyncedBody: "description_synced_body",
      syncState: "sync_state",
      serverCaptureId: "server_capture_id",
      serverMediaId: "server_media_id",
      uploadedBytes: "uploaded_bytes",
      syncedAt: "synced_at",
      attempts: "attempts",
      lastError: "last_error",
      localRevision: "local_revision",
      syncedRevision: "synced_revision",
    };

    const assignments: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    for (const [key, column] of Object.entries(columns)) {
      if (!(key in patch)) continue;
      const value = patch[key as keyof CaptureRecord];
      assignments.push(`${column} = ?`);
      // SQLite has no boolean type; store the flag as 0/1 so it round-trips.
      values.push(
        value === undefined ? null
          : typeof value === "boolean" ? (value ? 1 : 0)
          // merged_from is the one list-valued column; SQLite takes text.
          : Array.isArray(value) ? JSON.stringify(value)
          : (value as SQLite.SQLiteBindValue),
      );
    }

    // Bump here rather than at every call site: an edit made anywhere in the app
    // has to count, and a screen that forgot to say so would strand the change
    // exactly the way a post-sync description used to be stranded.
    const before = await this.get(uuid);
    if (before && patch.localRevision === undefined && isDirtyingChange(before, patch)) {
      assignments.push("local_revision = local_revision + 1");
    }

    if (assignments.length > 0) {
      values.push(uuid);
      await this.db.runAsync(
        `UPDATE captures SET ${assignments.join(", ")} WHERE uuid = ?`,
        values,
      );
    }

    const updated = await this.get(uuid);
    if (!updated) throw new CaptureNotFound(uuid);
    return updated;
  }

  /**
   * Delete a capture, releasing anything it had folded into itself.
   *
   * Deleting a merged capture un-merges it. Without this the parts keep a
   * `merged_into` pointing at a row that no longer exists, so `list()` goes on
   * hiding them and there is nothing left to clear the field from — recordings
   * still on disk, invisible forever. That is precisely the loss the merge
   * design exists to avoid, arrived at from the other direction.
   */
  async remove(uuid: string): Promise<void> {
    await this.db.runAsync(
      "UPDATE captures SET merged_into = NULL WHERE merged_into = ?", [uuid]);
    await this.db.runAsync("DELETE FROM captures WHERE uuid = ?", [uuid]);
  }

  async recoverInterrupted(): Promise<number> {
    // Failed rather than local, and with a reason: "it stopped and I do not
    // know why" is a different thing from "not sent yet", and the row is the
    // only place that difference can be recorded.
    const result = await this.db.runAsync(
      "UPDATE captures SET sync_state = 'failed', last_error = ? WHERE sync_state = 'syncing'",
      ["interrupted — the sync stopped before this capture finished"],
    );
    return result.changes;
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync(
      "UPDATE captures SET sync_state = 'local', server_capture_id = NULL, " +
        "server_media_id = NULL, uploaded_bytes = 0, synced_at = NULL, last_error = NULL",
    );
  }

  private toRecord(row: Row): CaptureRecord {
    return {
      uuid: row.uuid,
      mediaUuid: row.media_uuid,
      name: row.name ?? undefined,
      recordedAt: row.recorded_at,
      durationMs: row.duration_ms,
      sampleRate: row.sample_rate,
      channels: row.channels,
      audioPath: row.audio_path,
      bytes: row.bytes,
      videoPath: row.video_path ?? undefined,
      videoBytes: row.video_bytes ?? undefined,
      videoMediaUuid: row.video_media_uuid ?? undefined,
      videoServerMediaId: row.video_server_media_id ?? undefined,
      videoUploadedBytes: row.video_uploaded_bytes ?? undefined,
      inputDevice: row.input_device ?? undefined,
      inputHonoured:
        row.input_honoured === null || row.input_honoured === undefined
          ? undefined
          : row.input_honoured === 1,
      preRollSec: row.pre_roll_sec ?? undefined,
      appVersion: row.app_version ?? undefined,
      appCommit: row.app_commit ?? undefined,
      trigger: row.trigger === "auto" ? "auto" : undefined,
      observerRole: row.observer_role ?? undefined,
      distanceBand: row.distance_band ?? undefined,
      adultCount: row.adult_count ?? undefined,
      juvenileCount: row.juvenile_count ?? undefined,
      unagedCount: row.unaged_count ?? undefined,
      silentConfirmedAt: row.silent_confirmed_at ?? undefined,
      nothingToLabelAt: row.nothing_to_label_at ?? undefined,
      behaviorGuess: row.behavior_guess ?? undefined,
      mergedFrom: row.merged_from ? JSON.parse(row.merged_from) : undefined,
      mergedInto: row.merged_into ?? undefined,
      envelopeJson: row.envelope_json ?? undefined,
      cropStartSec: row.crop_start_sec ?? undefined,
      cropEndSec: row.crop_end_sec ?? undefined,
      keep: row.keep === 1,
      familyUuid: row.family_uuid ?? undefined,
      latitude: row.latitude ?? undefined,
      longitude: row.longitude ?? undefined,
      locationName: row.location_name ?? undefined,
      region: row.region ?? undefined,
      notes: row.notes ?? undefined,
      description: row.description ?? undefined,
      descriptionUuid: row.description_uuid ?? undefined,
      descriptionUpdatedAt: row.description_updated_at ?? undefined,
      descriptionSyncedAt: row.description_synced_at ?? undefined,
      descriptionSyncedBody: row.description_synced_body ?? undefined,
      syncState: row.sync_state,
      serverCaptureId: row.server_capture_id ?? undefined,
      serverMediaId: row.server_media_id ?? undefined,
      uploadedBytes: row.uploaded_bytes,
      syncedAt: row.synced_at ?? undefined,
      attempts: row.attempts,
      lastError: row.last_error ?? undefined,
      localRevision: row.local_revision ?? 0,
      syncedRevision: row.synced_revision ?? 0,
    };
  }
}
