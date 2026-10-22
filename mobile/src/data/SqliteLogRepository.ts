import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { LogRepository } from "./LogRepository";
import type { LogEntry, LogLevel, StoredLogEntry } from "../domain/logging";
import { LEVELS } from "../domain/logging";

/**
 * Cap on rows kept locally.
 *
 * Days of ordinary use, or one very bad afternoon. Beyond that the oldest go:
 * unlike a capture, a log line has no value that survives being superseded, and
 * a phone in a crash loop must not be able to fill the storage that field
 * recordings need.
 */
const KEEP_ROWS = 5000;

type Row = {
  uuid: string;
  at: string;
  level: string;
  tag: string;
  message: string;
  detail: string | null;
  synced_at: string | null;
};

/** The phone's log, on the phone. See domain/logging.ts for why. */
export class SqliteLogRepository implements LogRepository {
  private writes = 0;

  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteLogRepository> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS logs (
        uuid TEXT PRIMARY KEY NOT NULL,
        at TEXT NOT NULL,
        level TEXT NOT NULL,
        tag TEXT NOT NULL,
        message TEXT NOT NULL,
        detail TEXT,
        synced_at TEXT
      );
      CREATE INDEX IF NOT EXISTS logs_at ON logs (at);
      CREATE INDEX IF NOT EXISTS logs_pending ON logs (synced_at);
    `);
    return new SqliteLogRepository(db);
  }

  /**
   * Write a batch in one transaction.
   *
   * `OR IGNORE` because the same entry can legitimately arrive twice: the ring
   * buffer flushes on attach, and an entry written while that flush is in
   * flight is in both. Losing the duplicate is right; failing the batch is not.
   */
  async append(entries: LogEntry[]): Promise<void> {
    if (entries.length === 0) return;
    await this.db.withTransactionAsync(async () => {
      for (const entry of entries) {
        await this.db.runAsync(
          `INSERT OR IGNORE INTO logs (uuid, at, level, tag, message, detail)
           VALUES (?, ?, ?, ?, ?, ?)`,
          [
            entry.uuid,
            entry.at,
            entry.level,
            entry.tag,
            entry.message,
            entry.detail === undefined ? null : safeJson(entry.detail),
          ],
        );
      }
    });
    // Pruned occasionally rather than per write: the cap is a ceiling, not a
    // quota, and a DELETE with a subquery on every line would cost more than
    // the logging does.
    this.writes += entries.length;
    if (this.writes >= 200) {
      this.writes = 0;
      await this.prune();
    }
  }

  async recent({
    limit = 300,
    level,
    tag,
  }: { limit?: number; level?: LogLevel; tag?: string } = {}): Promise<StoredLogEntry[]> {
    const where: string[] = [];
    const params: SQLite.SQLiteBindValue[] = [];
    if (level) {
      const wanted = LEVELS.slice(LEVELS.indexOf(level));
      where.push(`level IN (${wanted.map(() => "?").join(",")})`);
      params.push(...wanted);
    }
    if (tag) {
      where.push("tag = ?");
      params.push(tag);
    }
    const clause = where.length > 0 ? `WHERE ${where.join(" AND ")}` : "";
    const rows = await this.db.getAllAsync<Row>(
      `SELECT * FROM logs ${clause} ORDER BY at DESC, rowid DESC LIMIT ?`,
      [...params, limit],
    );
    return rows.map(toEntry);
  }

  async pendingSync(limit = 500): Promise<StoredLogEntry[]> {
    const rows = await this.db.getAllAsync<Row>(
      "SELECT * FROM logs WHERE synced_at IS NULL ORDER BY at, rowid LIMIT ?",
      [limit],
    );
    return rows.map(toEntry);
  }

  async markSynced(uuids: string[]): Promise<void> {
    if (uuids.length === 0) return;
    const now = new Date().toISOString();
    await this.db.runAsync(
      `UPDATE logs SET synced_at = ? WHERE uuid IN (${uuids.map(() => "?").join(",")})`,
      [now, ...uuids],
    );
  }

  async countPending(): Promise<number> {
    const row = await this.db.getFirstAsync<{ n: number }>(
      "SELECT COUNT(*) n FROM logs WHERE synced_at IS NULL",
    );
    return row?.n ?? 0;
  }

  async clear(): Promise<void> {
    await this.db.runAsync("DELETE FROM logs");
  }

  async tags(): Promise<string[]> {
    const rows = await this.db.getAllAsync<{ tag: string }>(
      "SELECT DISTINCT tag FROM logs ORDER BY tag",
    );
    return rows.map((row) => row.tag);
  }

  /** Oldest first, synced or not — a sent line has already served its purpose. */
  private async prune(): Promise<void> {
    await this.db.runAsync(
      `DELETE FROM logs WHERE rowid NOT IN (
         SELECT rowid FROM logs ORDER BY rowid DESC LIMIT ?)`,
      [KEEP_ROWS],
    );
  }
}

function toEntry(row: Row): StoredLogEntry {
  return {
    uuid: row.uuid,
    at: row.at,
    level: row.level as LogLevel,
    tag: row.tag,
    message: row.message,
    detail: row.detail === null ? undefined : parse(row.detail),
    syncedAt: row.synced_at ?? undefined,
  };
}

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/**
 * Detail is written by failing code, so it may be circular, huge, or a native
 * object that does not survive stringify. None of that may take down the write.
 */
function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}
