/**
 * The slice of expo-sqlite the data layer uses, declared so the host test
 * build can typecheck the Sqlite* repositories.
 *
 * Resolving the real package pulls expo's own TypeScript sources into the
 * program, which do not compile under this tsconfig — that is why the whole
 * SQLite layer used to be excluded from typechecking, and how a fixture
 * drifting from an interface shipped unseen. tsconfig.tests.json maps
 * "expo-sqlite" here instead; the runtime lives in
 * tests/support/expoSqliteShim.ts and must match these shapes.
 */
declare module "expo-sqlite" {
  export type SQLiteBindValue = string | number | boolean | null | Uint8Array;

  export class SQLiteDatabase {
    execAsync(sql: string): Promise<void>;
    runAsync(
      sql: string,
      params?: SQLiteBindValue[],
    ): Promise<{ lastInsertRowId: number; changes: number }>;
    getAllAsync<T>(sql: string, params?: SQLiteBindValue[]): Promise<T[]>;
    getFirstAsync<T>(sql: string, params?: SQLiteBindValue[]): Promise<T | null>;
    withTransactionAsync(work: () => Promise<void>): Promise<void>;
  }

  export function openDatabaseAsync(name: string): Promise<SQLiteDatabase>;
}
