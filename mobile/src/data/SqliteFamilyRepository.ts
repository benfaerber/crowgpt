import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { FamilyRecord } from "../domain/families";
import type { FamilyRepository } from "./FamilyRepository";

type Row = {
  uuid: string;
  name: string;
  color: string;
  notes: string | null;
  created_at: string;
  server_id: number | null;
  synced_at: string | null;
};

export class SqliteFamilyRepository implements FamilyRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteFamilyRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS families (
        uuid TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL,
        server_id INTEGER,
        synced_at TEXT
      );
    `);
    return new SqliteFamilyRepository(db);
  }

  async add(family: Omit<FamilyRecord, "serverId" | "syncedAt">): Promise<FamilyRecord> {
    await this.db.runAsync(
      "INSERT INTO families (uuid, name, color, notes, created_at) VALUES (?, ?, ?, ?, ?)",
      [family.uuid, family.name, family.color, family.notes ?? null, family.createdAt],
    );
    return (await this.get(family.uuid))!;
  }

  async get(uuid: string): Promise<FamilyRecord | null> {
    const row = await this.db.getFirstAsync<Row>("SELECT * FROM families WHERE uuid = ?", [uuid]);
    return row ? this.toRecord(row) : null;
  }

  async list(): Promise<FamilyRecord[]> {
    const rows = await this.db.getAllAsync<Row>("SELECT * FROM families ORDER BY name");
    return rows.map((row) => this.toRecord(row));
  }

  async pendingSync(): Promise<FamilyRecord[]> {
    // On synced_at, not server_id: an edited family keeps its server id but
    // clears synced_at, and selecting on the id stranded the first
    // description edit on the phone while the row promised "syncs next push".
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM families WHERE synced_at IS NULL ORDER BY created_at",
    );
    return rows.map((row) => this.toRecord(row));
  }

  async update(uuid: string, patch: Partial<FamilyRecord>): Promise<FamilyRecord> {
    const columns: Record<keyof FamilyRecord, string> = {
      uuid: "uuid",
      name: "name",
      color: "color",
      notes: "notes",
      createdAt: "created_at",
      serverId: "server_id",
      syncedAt: "synced_at",
    };
    const assignments: string[] = [];
    const values: SQLite.SQLiteBindValue[] = [];
    for (const [key, column] of Object.entries(columns)) {
      if (!(key in patch)) continue;
      const value = patch[key as keyof FamilyRecord];
      assignments.push(`${column} = ?`);
      values.push(value === undefined ? null : (value as SQLite.SQLiteBindValue));
    }
    if (assignments.length > 0) {
      values.push(uuid);
      await this.db.runAsync(`UPDATE families SET ${assignments.join(", ")} WHERE uuid = ?`, values);
    }
    return (await this.get(uuid))!;
  }

  async remove(uuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM families WHERE uuid = ?", [uuid]);
  }

  private toRecord(row: Row): FamilyRecord {
    return {
      uuid: row.uuid,
      name: row.name,
      color: row.color,
      notes: row.notes ?? undefined,
      createdAt: row.created_at,
      serverId: row.server_id ?? undefined,
      syncedAt: row.synced_at ?? undefined,
    };
  }
}
