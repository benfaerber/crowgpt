import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import { LabelNotFound, type LabelRepository } from "./LabelRepository";
import { ensureColumns } from "./sqliteMigrations";
import type { LabelRecord, NewLabel } from "../domain/labels";

type Row = {
  uuid: string;
  capture_uuid: string;
  call_type: string;
  species: string;
  start_sec: number;
  end_sec: number;
  from_detection: number | null;
  config_version: number | null;
  caller_role: string | null;
  created_at: string;
  server_id: number | null;
  synced_at: string | null;
};

export class SqliteLabelRepository implements LabelRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteLabelRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS labels (
        uuid TEXT PRIMARY KEY NOT NULL,
        capture_uuid TEXT NOT NULL,
        call_type TEXT NOT NULL,
        species TEXT NOT NULL,
        start_sec REAL NOT NULL,
        end_sec REAL NOT NULL,
        from_detection INTEGER,
        created_at TEXT NOT NULL,
        server_id INTEGER,
        synced_at TEXT
      );
      CREATE INDEX IF NOT EXISTS labels_capture ON labels (capture_uuid);
    `);
    // Anything added to the schema above after a build has shipped also belongs
    // here, or installs that already have the table never get it.
    await ensureColumns(db, "labels", [
      ["from_detection", "INTEGER"],
      // Nullable: labels made before the vocabulary was versioned have no
      // honest answer, and a guessed one would be worse than none.
      ["config_version", "INTEGER"],
      // Nullable, and NULL means nobody looked — which is not the same as
      // nobody being there. Never defaulted for that reason.
      ["caller_role", "TEXT"],
    ]);
    return new SqliteLabelRepository(db);
  }

  async add(label: NewLabel): Promise<LabelRecord> {
    await this.db.runAsync(
      `INSERT INTO labels (uuid, capture_uuid, call_type, species, start_sec,
                           end_sec, from_detection, config_version, caller_role,
                           created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        label.uuid,
        label.captureUuid,
        label.callType,
        label.species,
        label.startSec,
        label.endSec,
        label.fromDetection ? 1 : 0,
        label.configVersion ?? null,
        label.callerRole ?? null,
        label.createdAt,
      ],
    );
    return { ...label };
  }

  async forCapture(captureUuid: string): Promise<LabelRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM labels WHERE capture_uuid = ? ORDER BY start_sec",
      [captureUuid],
    );
    return rows.map(toRecord);
  }

  async countsByCapture(): Promise<Map<string, number>> {
    const rows = await this.db.getAllAsync<{ capture_uuid: string; n: number }>(
      "SELECT capture_uuid, COUNT(*) AS n FROM labels GROUP BY capture_uuid",
    );
    return new Map(rows.map((row) => [row.capture_uuid, row.n]));
  }

  async remove(uuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM labels WHERE uuid = ?", [uuid]);
  }

  async update(uuid: string, patch: Partial<LabelRecord>): Promise<LabelRecord> {
    const columns: Record<keyof LabelRecord, string> = {
      uuid: "uuid",
      captureUuid: "capture_uuid",
      callType: "call_type",
      species: "species",
      startSec: "start_sec",
      endSec: "end_sec",
      callerRole: "caller_role",
      fromDetection: "from_detection",
      configVersion: "config_version",
      createdAt: "created_at",
      serverId: "server_id",
      syncedAt: "synced_at",
    };
    const assignments: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    for (const [key, column] of Object.entries(columns)) {
      if (!(key in patch)) continue;
      const value = patch[key as keyof LabelRecord];
      assignments.push(`${column} = ?`);
      values.push(
        value === undefined
          ? null
          : typeof value === "boolean"
            ? (value ? 1 : 0)
            : (value as SQLite.SQLiteBindValue),
      );
    }
    if (assignments.length > 0) {
      values.push(uuid);
      await this.db.runAsync(
        `UPDATE labels SET ${assignments.join(", ")} WHERE uuid = ?`,
        values,
      );
    }
    const row = await this.db.getFirstAsync<Row>(
      "SELECT * FROM labels WHERE uuid = ?",
      [uuid],
    );
    if (!row) throw new LabelNotFound(uuid);
    return toRecord(row);
  }

  async byCallType(callType: string, limit = 5): Promise<LabelRecord[]> {
    // Newest first: a recent example is more likely to be from the same birds
    // and the same place, which is what makes it a useful comparison.
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM labels WHERE call_type = ? ORDER BY created_at DESC LIMIT ?",
      [callType, limit],
    );
    return rows.map(toRecord);
  }

  async pendingSync(): Promise<LabelRecord[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM labels WHERE server_id IS NULL ORDER BY created_at",
    );
    return rows.map(toRecord);
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync("UPDATE labels SET server_id = NULL, synced_at = NULL");
  }
}

function toRecord(row: Row): LabelRecord {
  return {
    uuid: row.uuid,
    captureUuid: row.capture_uuid,
    callType: row.call_type,
    species: row.species,
    startSec: row.start_sec,
    endSec: row.end_sec,
    fromDetection: row.from_detection === 1,
    configVersion: row.config_version ?? undefined,
    callerRole: row.caller_role ?? undefined,
    createdAt: row.created_at,
    serverId: row.server_id ?? undefined,
    syncedAt: row.synced_at ?? undefined,
  };
}
