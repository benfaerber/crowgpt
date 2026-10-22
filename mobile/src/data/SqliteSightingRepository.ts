import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { SightingRepository } from "./SightingRepository";
import type { NewSighting, SightingRecord } from "../domain/sightings";

type Row = {
  uuid: string;
  capture_uuid: string;
  key: string;
  offset_sec: number;
  distance_m: number | null;
  notes: string | null;
  created_at: string;
  server_id: number | null;
  synced_at: string | null;
};

/** Out-of-frame sightings, held locally until the next sync. See domain/sightings.ts. */
export class SqliteSightingRepository implements SightingRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteSightingRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS sightings (
        uuid TEXT PRIMARY KEY NOT NULL,
        capture_uuid TEXT NOT NULL,
        key TEXT NOT NULL,
        offset_sec REAL NOT NULL,
        distance_m REAL,
        notes TEXT,
        created_at TEXT NOT NULL,
        server_id INTEGER,
        synced_at TEXT
      );
      CREATE INDEX IF NOT EXISTS sightings_capture ON sightings (capture_uuid);
    `);
    return new SqliteSightingRepository(db);
  }

  async add(sighting: NewSighting): Promise<SightingRecord> {
    await this.db.runAsync(
      `INSERT INTO sightings (uuid, capture_uuid, key, offset_sec, distance_m,
                              notes, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        sighting.uuid,
        sighting.captureUuid,
        sighting.key,
        sighting.offsetSec,
        sighting.distanceM ?? null,
        sighting.notes ?? null,
        sighting.createdAt,
      ],
    );
    return { ...sighting };
  }

  async forCapture(captureUuid: string): Promise<SightingRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM sightings WHERE capture_uuid = ? ORDER BY offset_sec",
      [captureUuid],
    );
    return rows.map(toRecord);
  }

  async remove(uuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM sightings WHERE uuid = ?", [uuid]);
  }

  async update(uuid: string, patch: Partial<SightingRecord>): Promise<SightingRecord> {
    const columns: Record<keyof SightingRecord, string> = {
      uuid: "uuid",
      captureUuid: "capture_uuid",
      key: "key",
      offsetSec: "offset_sec",
      distanceM: "distance_m",
      notes: "notes",
      createdAt: "created_at",
      serverId: "server_id",
      syncedAt: "synced_at",
    };
    const assignments: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    for (const [field, column] of Object.entries(columns)) {
      if (!(field in patch)) continue;
      const value = patch[field as keyof SightingRecord];
      assignments.push(`${column} = ?`);
      values.push(value === undefined ? null : (value as SQLite.SQLiteBindValue));
    }
    if (assignments.length > 0) {
      values.push(uuid);
      await this.db.runAsync(
        `UPDATE sightings SET ${assignments.join(", ")} WHERE uuid = ?`,
        values,
      );
    }
    const row = await this.db.getFirstAsync<Row>(
      "SELECT * FROM sightings WHERE uuid = ?",
      [uuid],
    );
    if (!row) throw new Error(`no sighting ${uuid}`);
    return toRecord(row);
  }

  async pendingSync(): Promise<SightingRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM sightings WHERE server_id IS NULL ORDER BY created_at",
    );
    return rows.map(toRecord);
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync("UPDATE sightings SET server_id = NULL, synced_at = NULL");
  }
}

function toRecord(row: Row): SightingRecord {
  return {
    uuid: row.uuid,
    captureUuid: row.capture_uuid,
    key: row.key,
    offsetSec: row.offset_sec,
    distanceM: row.distance_m ?? undefined,
    notes: row.notes ?? undefined,
    createdAt: row.created_at,
    serverId: row.server_id ?? undefined,
    syncedAt: row.synced_at ?? undefined,
  };
}
