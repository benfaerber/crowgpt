import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";
import type { ScoutVisitRepository } from "./ScoutVisitRepository";
import type { ScoutVisit, VisitKind, VisitOutcome } from "../domain/scoutVisits";

/** Scout marks, held locally until the next push. See domain/scoutVisits.ts. */
export class SqliteScoutVisitRepository implements ScoutVisitRepository {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteScoutVisitRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS scout_visits (
        uuid TEXT PRIMARY KEY NOT NULL,
        kind TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        outcome TEXT NOT NULL,
        note TEXT,
        visited_at TEXT NOT NULL,
        server_id INTEGER,
        synced_at TEXT
      );
    `);
    return new SqliteScoutVisitRepository(db);
  }

  async add(visit: ScoutVisit): Promise<void> {
    await this.db.runAsync(
      `INSERT OR IGNORE INTO scout_visits
       (uuid, kind, latitude, longitude, outcome, note, visited_at, server_id, synced_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [visit.uuid, visit.kind, visit.latitude, visit.longitude, visit.outcome,
       visit.note ?? null, visit.visitedAt, visit.serverId ?? null,
       visit.syncedAt ?? null],
    );
  }

  async all(): Promise<ScoutVisit[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM scout_visits ORDER BY visited_at");
    return rows.map(toVisit);
  }

  async pendingSync(limit: number): Promise<ScoutVisit[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM scout_visits WHERE server_id IS NULL "
      + "ORDER BY visited_at LIMIT ?", [limit]);
    return rows.map(toVisit);
  }

  async markSynced(uuid: string, serverId: number, syncedAt: string): Promise<void> {
    await this.db.runAsync(
      "UPDATE scout_visits SET server_id = ?, synced_at = ? WHERE uuid = ?",
      [serverId, syncedAt, uuid]);
  }

  async forgetServerState(): Promise<void> {
    await this.db.runAsync(
      "UPDATE scout_visits SET server_id = NULL, synced_at = NULL");
  }
}

interface Row {
  uuid: string;
  kind: string;
  latitude: number;
  longitude: number;
  outcome: string;
  note: string | null;
  visited_at: string;
  server_id: number | null;
  synced_at: string | null;
}

function toVisit(row: Row): ScoutVisit {
  return {
    uuid: row.uuid,
    kind: row.kind as VisitKind,
    latitude: row.latitude,
    longitude: row.longitude,
    outcome: row.outcome as VisitOutcome,
    note: row.note ?? undefined,
    visitedAt: row.visited_at,
    serverId: row.server_id ?? undefined,
    syncedAt: row.synced_at ?? undefined,
  };
}
