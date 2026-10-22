import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import { DictationNotFound, type DictationRepository } from "./DictationRepository";
import { isPendingSync, type DictationRecord, type NewDictation } from "../domain/dictations";

type Row = {
  uuid: string;
  capture_uuid: string;
  audio_path: string;
  recorded_at: string;
  duration_ms: number;
  bytes: number;
  sample_rate: number;
  channels: number;
  input_device: string | null;
  input_honoured: number | null;
  state: string;
  server_id: number | null;
  uploaded_bytes: number;
  synced_at: string | null;
  transcript: string | null;
  transcript_at: string | null;
};

/** Spoken notes, held locally until the next sync. See domain/dictations.ts. */
export class SqliteDictationRepository implements DictationRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteDictationRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS dictations (
        uuid TEXT PRIMARY KEY NOT NULL,
        capture_uuid TEXT NOT NULL,
        audio_path TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        bytes INTEGER NOT NULL DEFAULT 0,
        sample_rate INTEGER NOT NULL,
        channels INTEGER NOT NULL,
        input_device TEXT,
        input_honoured INTEGER,
        state TEXT NOT NULL DEFAULT 'recording',
        server_id INTEGER,
        uploaded_bytes INTEGER NOT NULL DEFAULT 0,
        synced_at TEXT,
        transcript TEXT,
        transcript_at TEXT
      );
      CREATE INDEX IF NOT EXISTS dictations_capture ON dictations (capture_uuid);
    `);
    return new SqliteDictationRepository(db);
  }

  async add(dictation: NewDictation): Promise<DictationRecord> {
    await this.db.runAsync(
      `INSERT INTO dictations (uuid, capture_uuid, audio_path, recorded_at,
                               duration_ms, bytes, sample_rate, channels,
                               input_device, input_honoured, state, uploaded_bytes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)`,
      [
        dictation.uuid,
        dictation.captureUuid,
        dictation.audioPath,
        dictation.recordedAt,
        dictation.durationMs,
        dictation.bytes,
        dictation.sampleRate,
        dictation.channels,
        dictation.inputDevice ?? null,
        dictation.inputHonoured === undefined ? null : Number(dictation.inputHonoured),
        dictation.state,
      ],
    );
    return { ...dictation, uploadedBytes: 0 };
  }

  async get(uuid: string): Promise<DictationRecord | null> {
    const row = await this.db.getFirstAsync<Row>(
      "SELECT * FROM dictations WHERE uuid = ?", [uuid]);
    return row ? toRecord(row) : null;
  }

  async forCapture(captureUuid: string): Promise<DictationRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM dictations WHERE capture_uuid = ? ORDER BY recorded_at",
      [captureUuid],
    );
    return rows.map(toRecord);
  }

  async forCaptures(captureUuids: readonly string[]): Promise<DictationRecord[]> {
    if (captureUuids.length === 0) return [];
    const holes = captureUuids.map(() => "?").join(",");
    const rows = await this.db.getAllAsync<Row>(
      `SELECT * FROM dictations WHERE capture_uuid IN (${holes}) ORDER BY recorded_at`,
      [...captureUuids],
    );
    return rows.map(toRecord);
  }

  async pendingSync(): Promise<DictationRecord[]> {
    // Filtered in the domain rather than in SQL: "what may be sent" is a rule
    // with a reason attached, and two copies of it drift.
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM dictations ORDER BY recorded_at");
    return rows.map(toRecord).filter(isPendingSync);
  }

  async stale(): Promise<DictationRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM dictations WHERE state = 'recording' ORDER BY recorded_at");
    return rows.map(toRecord);
  }

  async update(uuid: string, patch: Partial<DictationRecord>): Promise<DictationRecord> {
    const columns: Record<keyof DictationRecord, string> = {
      uuid: "uuid",
      captureUuid: "capture_uuid",
      audioPath: "audio_path",
      recordedAt: "recorded_at",
      durationMs: "duration_ms",
      bytes: "bytes",
      sampleRate: "sample_rate",
      channels: "channels",
      inputDevice: "input_device",
      inputHonoured: "input_honoured",
      state: "state",
      serverId: "server_id",
      uploadedBytes: "uploaded_bytes",
      syncedAt: "synced_at",
      transcript: "transcript",
      transcriptAt: "transcript_at",
    };
    const sets: string[] = [];
    const values: (string | number | null)[] = [];
    for (const [key, column] of Object.entries(columns)) {
      if (!(key in patch)) continue;
      const value = patch[key as keyof DictationRecord];
      sets.push(`${column} = ?`);
      values.push(
        value === undefined ? null
          : typeof value === "boolean" ? Number(value)
            : (value as string | number));
    }
    if (sets.length > 0) {
      await this.db.runAsync(
        `UPDATE dictations SET ${sets.join(", ")} WHERE uuid = ?`, [...values, uuid]);
    }
    const updated = await this.get(uuid);
    if (!updated) throw new DictationNotFound(uuid);
    return updated;
  }

  async remove(uuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM dictations WHERE uuid = ?", [uuid]);
  }

  async audioPaths(): Promise<string[]> {
    const rows = await this.db.getAllAsync<{ audio_path: string }>(
      "SELECT audio_path FROM dictations");
    return rows.map((row) => row.audio_path);
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync(
      "UPDATE dictations SET server_id = NULL, uploaded_bytes = 0, synced_at = NULL");
  }
}

function toRecord(row: Row): DictationRecord {
  return {
    uuid: row.uuid,
    captureUuid: row.capture_uuid,
    audioPath: row.audio_path,
    recordedAt: row.recorded_at,
    durationMs: row.duration_ms,
    bytes: row.bytes,
    sampleRate: row.sample_rate,
    channels: row.channels,
    inputDevice: row.input_device ?? undefined,
    inputHonoured: row.input_honoured === null ? undefined : Boolean(row.input_honoured),
    state: row.state as DictationRecord["state"],
    serverId: row.server_id ?? undefined,
    uploadedBytes: row.uploaded_bytes,
    syncedAt: row.synced_at ?? undefined,
    transcript: row.transcript ?? undefined,
    transcriptAt: row.transcript_at ?? undefined,
  };
}
