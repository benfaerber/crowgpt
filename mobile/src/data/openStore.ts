import * as SQLite from "expo-sqlite";

/**
 * The one handle on the phone's database.
 *
 * Every store used to open its own — captures, families, labels, context,
 * sightings, settings, logs, migrations, eight of them — on the reasonable
 * assumption that eight handles means eight connections. It does not.
 * expo-sqlite caches by path: opening the same file again hands back the *same*
 * native connection with its reference count bumped.
 *
 * That would be fine, except the reference count only guards the explicit
 * close. When a JS handle is garbage collected, `NativeDatabase.
 * sharedObjectDidRelease` calls `ref.close()` outright, and since every handle
 * wraps one shared connection, the first one collected closes the database
 * *for all of them*. Every later query then prepares a statement against a
 * closed connection, which is the NullPointerException in `prepareAsync` —
 * random, because it depends on when Hermes decides to collect, and worse on
 * the phone with the most captures.
 *
 * It is also, almost certainly, "all my captures disappeared… and they came
 * back somehow": the read threw, the list rendered empty, and the next launch
 * opened a fresh connection.
 *
 * So: one handle, opened once, shared. Nothing to collect while the app runs.
 * The promise is memoised rather than the database, so concurrent callers at
 * startup — which is all of them — wait on the same open rather than racing to
 * start eight.
 */
const handles = new Map<string, Promise<SQLite.SQLiteDatabase>>();

export function openStore(name = "cawtalker.db"): Promise<SQLite.SQLiteDatabase> {
  const existing = handles.get(name);
  if (existing) return existing;
  const opening = open(name).catch((failure) => {
    // A failed open must not be cached, or every later caller gets the same
    // rejection forever and the app is dead until it is restarted.
    handles.delete(name);
    throw failure;
  });
  handles.set(name, opening);
  return opening;
}

async function open(name: string): Promise<SQLite.SQLiteDatabase> {
  const db = await SQLite.openDatabaseAsync(name);
  await db.execAsync(`
    -- Readers and writers stop blocking each other. A property of the file
    -- rather than of the connection, so it survives across launches.
    PRAGMA journal_mode = WAL;
    -- Per connection. Without it SQLite does not wait for a lock, it gives up
    -- immediately — so a read during a write throws \`database is locked\`, once,
    -- at random. Five seconds is far longer than any write here takes and far
    -- shorter than a person notices.
    PRAGMA busy_timeout = 5000;
    PRAGMA foreign_keys = ON;
  `);
  return db;
}
