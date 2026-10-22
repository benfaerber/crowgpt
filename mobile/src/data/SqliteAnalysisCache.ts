import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { AnalysisCache, CachedAnalysis } from "./AnalysisCache";
import type { DetectedCall } from "../net/serverTypes";

type Row = {
  capture_uuid: string;
  calls: string;
  waveform: string;
  duration: number | null;
  fetched_at: string;
};

/**
 * The analysis cache, on the phone. See AnalysisCache.ts for why it exists.
 *
 * One row per capture holding the whole answer as JSON, rather than a table of
 * calls. The read is always "everything about this capture" and nothing here is
 * ever queried across captures — a normalised schema would buy nothing and cost
 * a migration every time the analyzer returns a new field.
 */
export class SqliteAnalysisCache implements AnalysisCache {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open(name = "cawtalker.db"): Promise<SqliteAnalysisCache> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS analysis_cache (
        capture_uuid TEXT PRIMARY KEY NOT NULL,
        calls TEXT NOT NULL,
        waveform TEXT NOT NULL,
        duration REAL,
        fetched_at TEXT NOT NULL
      );
    `);
    return new SqliteAnalysisCache(db);
  }

  async get(captureUuid: string): Promise<CachedAnalysis | undefined> {
    const row = await this.db.getFirstAsync<Row>(
      "SELECT * FROM analysis_cache WHERE capture_uuid = ?",
      [captureUuid],
    );
    if (!row) return undefined;
    return {
      calls: parse<DetectedCall[]>(row.calls, []),
      waveform: parse<number[]>(row.waveform, []),
      duration: row.duration ?? undefined,
      fetchedAt: row.fetched_at,
    };
  }

  async save(
    captureUuid: string,
    analysis: Omit<CachedAnalysis, "fetchedAt">,
  ): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO analysis_cache (capture_uuid, calls, waveform, duration, fetched_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(capture_uuid) DO UPDATE SET
         calls = excluded.calls,
         waveform = excluded.waveform,
         duration = excluded.duration,
         fetched_at = excluded.fetched_at`,
      [
        captureUuid,
        JSON.stringify(analysis.calls ?? []),
        JSON.stringify(analysis.waveform ?? []),
        analysis.duration ?? null,
        new Date().toISOString(),
      ],
    );
  }

  async forget(captureUuid: string): Promise<void> {
    await this.db.runAsync("DELETE FROM analysis_cache WHERE capture_uuid = ?", [
      captureUuid,
    ]);
  }
}

function parse<T>(text: string, fallback: T): T {
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}
