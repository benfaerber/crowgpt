/**
 * Just enough of a database to migrate one.
 *
 * Structural rather than `expo-sqlite`'s own type, so this module and the
 * migration list stay importable by the host test run — importing the real type
 * pulls expo's TypeScript sources into a program compiled with different
 * settings, and they do not survive it.
 */
export interface MigratableDb {
  execAsync(source: string): Promise<void>;
  getAllAsync<T>(source: string): Promise<T[]>;
}

/**
 * Ordered, run-once schema changes for the phone's store.
 *
 * Every store used to reshape its own tables on open, guessing at the current
 * shape each time: `CREATE TABLE IF NOT EXISTS` for the original columns, then
 * "add this column if it isn't there" checks for everything since. That works
 * only for adding nullable columns, and only if whoever adds the next one
 * remembers to write the check.
 *
 * Forgetting once bricked the app. A new store shipped with `label_uuid` in its
 * `CREATE TABLE` and no check, so an installed phone never gained the column and
 * the index naming it threw — at open, before any screen rendered, which reads
 * as the whole app being broken rather than one feature missing.
 *
 * A migration here runs once, in order, and is recorded in `user_version`. That
 * makes a table rebuild — the only way SQLite changes a NOT NULL or a type — as
 * ordinary as adding a column, and makes "what shape is this database in?" a
 * question with an answer.
 */
export interface Migration {
  /** Human-readable, for the log. Order is what actually identifies a step. */
  readonly name: string;
  readonly up: (db: MigratableDb) => Promise<void>;
}

/**
 * Apply anything this database has not run yet.
 *
 * `user_version` is a counter SQLite keeps in the file itself, so the ledger
 * costs no table and survives anything short of deleting the database.
 *
 * Steps are identified by *position*, so migrations may only ever be appended.
 * Inserting one in the middle silently re-runs everything after it against a
 * database that already applied them, under the wrong names.
 */
export async function migrate(
  db: MigratableDb,
  migrations: readonly Migration[],
): Promise<string[]> {
  const [{ user_version: current }] = await db.getAllAsync<{ user_version: number }>(
    "PRAGMA user_version",
  );
  const pending = migrations.slice(current);
  const ran: string[] = [];

  for (const [offset, migration] of pending.entries()) {
    await migration.up(db);
    // Written per step rather than once at the end: a run interrupted halfway
    // must not repeat the steps that already succeeded.
    await db.execAsync(`PRAGMA user_version = ${current + offset + 1}`);
    ran.push(migration.name);
  }
  return ran;
}

/**
 * A migration that adds a column, tolerating one already added.
 *
 * The tolerance is for databases carrying columns the old open-time checks put
 * there: those were never recorded, so a fresh ledger has to assume nothing
 * about what is present.
 */
export function addColumn(table: string, column: string, decl: string): Migration {
  return {
    name: `add ${table}.${column}`,
    up: async (db) => {
      const columns = await db.getAllAsync<{ name: string }>(
        `PRAGMA table_info(${table})`,
      );
      if (!columns.some((row) => row.name === column)) {
        await db.execAsync(`ALTER TABLE ${table} ADD COLUMN ${column} ${decl}`);
      }
    },
  };
}

/** A migration that runs plain SQL. */
export function sql(name: string, statements: string): Migration {
  return { name, up: (db) => db.execAsync(statements) };
}
