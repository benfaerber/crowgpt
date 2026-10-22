import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { ContextRepository } from "./ContextRepository";
import { ensureColumns } from "./sqliteMigrations";
import type { ContextRecord, NewContext } from "../domain/context";

type Row = {
  uuid: string;
  capture_uuid: string;
  /** Null for a capture-level event, and for rows written before the column existed. */
  label_uuid: string | null;
  key: string;
  start_sec: number | null;
  end_sec: number | null;
  notes: string | null;
  config_version: number | null;
  created_at: string;
  server_id: number | null;
  synced_at: string | null;
};

/** Witnessed context, held locally until the next sync. See domain/context.ts. */
export class SqliteContextRepository implements ContextRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteContextRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS context_events (
        uuid TEXT PRIMARY KEY NOT NULL,
        capture_uuid TEXT NOT NULL,
        key TEXT NOT NULL,
        start_sec REAL,
        end_sec REAL,
        notes TEXT,
        created_at TEXT NOT NULL,
        server_id INTEGER,
        synced_at TEXT
      );
      CREATE INDEX IF NOT EXISTS context_capture ON context_events (capture_uuid);
    `);

    // `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists,
    // so a column added after an install has shipped has to be added in place.
    // Without this the app cannot even open its store — the index below names a
    // column the phone's copy of the table has never had.
    await ensureColumns(db, "context_events", [
      ["label_uuid", "TEXT"],
      ["config_version", "INTEGER"],
    ]);
    await db.execAsync(
      "CREATE INDEX IF NOT EXISTS context_label ON context_events (label_uuid);",
    );
    return new SqliteContextRepository(db);
  }

  async add(event: NewContext): Promise<ContextRecord> {
    await this.db.runAsync(
      `INSERT INTO context_events (uuid, capture_uuid, label_uuid, key, start_sec,
                                   end_sec, notes, config_version, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        event.uuid,
        event.captureUuid,
        event.labelUuid ?? null,
        event.key,
        event.startSec ?? null,
        event.endSec ?? null,
        event.notes ?? null,
        event.configVersion ?? null,
        event.createdAt,
      ],
    );
    return { ...event };
  }

  async forLabel(labelUuid: string): Promise<ContextRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM context_events WHERE label_uuid = ? ORDER BY created_at",
      [labelUuid],
    );
    return rows.map(toRecord);
  }

  async forCapture(captureUuid: string): Promise<ContextRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM context_events WHERE capture_uuid = ? ORDER BY created_at",
      [captureUuid],
    );
    return rows.map(toRecord);
  }

  async remove(uuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM context_events WHERE uuid = ?", [uuid]);
  }

  async update(uuid: string, patch: Partial<ContextRecord>): Promise<ContextRecord> {
    const columns: Record<keyof ContextRecord, string> = {
      uuid: "uuid",
      captureUuid: "capture_uuid",
      labelUuid: "label_uuid",
      key: "key",
      startSec: "start_sec",
      endSec: "end_sec",
      notes: "notes",
      configVersion: "config_version",
      createdAt: "created_at",
      serverId: "server_id",
      syncedAt: "synced_at",
    };
    const assignments: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    for (const [field, column] of Object.entries(columns)) {
      if (!(field in patch)) continue;
      const value = patch[field as keyof ContextRecord];
      assignments.push(`${column} = ?`);
      values.push(value === undefined ? null : (value as SQLite.SQLiteBindValue));
    }
    if (assignments.length > 0) {
      values.push(uuid);
      await this.db.runAsync(
        `UPDATE context_events SET ${assignments.join(", ")} WHERE uuid = ?`,
        values,
      );
    }
    const row = await this.db.getFirstAsync<Row>(
      "SELECT * FROM context_events WHERE uuid = ?",
      [uuid],
    );
    if (!row) throw new Error(`no context event ${uuid}`);
    return toRecord(row);
  }

  async pendingSync(): Promise<ContextRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM context_events WHERE server_id IS NULL ORDER BY created_at",
    );
    return rows.map(toRecord);
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync(
      "UPDATE context_events SET server_id = NULL, synced_at = NULL",
    );
  }
}

function toRecord(row: Row): ContextRecord {
  return {
    uuid: row.uuid,
    captureUuid: row.capture_uuid,
    // undefined, not "": an empty string is a label uuid that does not exist,
    // and this row deliberately has none.
    labelUuid: row.label_uuid ?? undefined,
    key: row.key,
    startSec: row.start_sec ?? undefined,
    endSec: row.end_sec ?? undefined,
    notes: row.notes ?? undefined,
    configVersion: row.config_version ?? undefined,
    createdAt: row.created_at,
    serverId: row.server_id ?? undefined,
    syncedAt: row.synced_at ?? undefined,
  };
}
