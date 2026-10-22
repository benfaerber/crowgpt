import type * as SQLite from "expo-sqlite";

/**
 * Add columns an already-installed database is missing.
 *
 * `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so
 * the schema written there only ever applies to a phone that has never run the
 * app. Every column added after a build ships has to be added in place, or the
 * app fails against its own store — and it fails at *open*, which reads as the
 * whole app being broken rather than one feature missing.
 *
 * That is exactly how `context_events.label_uuid` bricked v103: the table was
 * already there from v101, the new column never arrived, and the index naming it
 * threw before any screen rendered.
 */
export async function ensureColumns(
  db: SQLite.SQLiteDatabase,
  table: string,
  columns: readonly (readonly [name: string, decl: string])[],
): Promise<void> {
  const existing = await db.getAllAsync<{ name: string }>(`PRAGMA table_info(${table})`);
  const have = new Set(existing.map((row) => row.name));
  for (const [name, decl] of columns) {
    if (!have.has(name)) {
      await db.execAsync(`ALTER TABLE ${table} ADD COLUMN ${name} ${decl}`);
    }
  }
}
