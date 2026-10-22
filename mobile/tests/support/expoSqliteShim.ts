/**
 * expo-sqlite, impersonated over node:sqlite for the host-side tests.
 *
 * The Sqlite* repositories were the one layer no test could touch: they import
 * expo-sqlite, which only exists on a device — so every test ran against the
 * Memory* fakes, and nothing checked the two implementations agreed. That gap
 * has already cost data once: video fields added to `update` but not to the
 * INSERT silently dropped a filmed capture's video the instant it was saved.
 *
 * vitest aliases "expo-sqlite" to this file (see vitest.config.ts), which
 * implements exactly the five methods the repositories use, backed by an
 * in-memory database per opened name. Real SQL against a real SQLite —
 * node's — so column typos, constraint violations and NULL handling fail
 * here the way they would on the phone.
 */

// eslint-disable-next-line import/no-unresolved -- node builtin, present on the test host
import { DatabaseSync } from "node:sqlite";

export type SQLiteBindValue = string | number | boolean | null | Uint8Array;

export class SQLiteDatabase {
  private readonly db = new DatabaseSync(":memory:");

  async execAsync(sql: string): Promise<void> {
    this.db.exec(sql);
  }

  async runAsync(
    sql: string,
    params?: SQLiteBindValue[],
  ): Promise<{ lastInsertRowId: number; changes: number }> {
    const result = this.db.prepare(sql).run(...bindable(params));
    return {
      lastInsertRowId: Number(result.lastInsertRowid),
      changes: Number(result.changes),
    };
  }

  async getAllAsync<T>(sql: string, params?: SQLiteBindValue[]): Promise<T[]> {
    return this.db.prepare(sql).all(...bindable(params)) as T[];
  }

  async getFirstAsync<T>(sql: string, params?: SQLiteBindValue[]): Promise<T | null> {
    return (this.db.prepare(sql).get(...bindable(params)) as T | undefined) ?? null;
  }

  async withTransactionAsync(work: () => Promise<void>): Promise<void> {
    this.db.exec("BEGIN");
    try {
      await work();
      this.db.exec("COMMIT");
    } catch (failure) {
      this.db.exec("ROLLBACK");
      throw failure;
    }
  }
}

/** node:sqlite refuses booleans and undefined; expo-sqlite tolerates both. */
function bindable(params?: SQLiteBindValue[]): (string | number | null | Uint8Array)[] {
  return (params ?? []).map((value) =>
    value === undefined ? null
      : typeof value === "boolean" ? (value ? 1 : 0)
      : value,
  );
}

export async function openDatabaseAsync(_name: string): Promise<SQLiteDatabase> {
  // A fresh in-memory database per open. openStore memoises per name, so one
  // test's repositories share a database exactly the way the app's do, and
  // tests isolate by opening distinct names.
  return new SQLiteDatabase();
}
