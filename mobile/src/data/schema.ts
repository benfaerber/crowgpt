import { addColumn, sql, type Migration } from "./migrations";

/**
 * The one migration list for the phone's database.
 *
 * One list because there is one file — every store opens `cawtalker.db`, and
 * `user_version` is a property of the file, not of a table. Two stores keeping
 * their own ledgers in the same counter would each skip the other's steps.
 *
 * Steps are identified by *position*, so this may only ever be appended to.
 * Inserting one in the middle re-runs everything after it against a database
 * that already applied them.
 *
 * Run after every store has opened, so the tables a step rebuilds exist — see
 * runMigrations.ts, which is kept separate because it touches expo-sqlite and
 * this list is imported by the host test run.
 */
export const MIGRATIONS: readonly Migration[] = [
  sql(
    "context_events.label_uuid may be null",
    `
    -- A capture-level context event has no call to hang off, which is legal
    -- only on a recording confirmed to hold no calls. The table shipped with
    -- label_uuid NOT NULL before that existed, and CREATE TABLE IF NOT EXISTS
    -- never revisits a table that is already there — so every phone installed
    -- since carries a constraint the code stopped intending, and tagging a
    -- silent capture failed with "NOT NULL constraint failed".
    --
    -- SQLite cannot drop a NOT NULL, so the table is rebuilt. Copying by
    -- explicit column list rather than SELECT *, because the column order of
    -- the old table depends on which build created it.
    CREATE TABLE context_events_rebuilt (
      uuid TEXT PRIMARY KEY NOT NULL,
      capture_uuid TEXT NOT NULL,
      label_uuid TEXT,
      key TEXT NOT NULL,
      start_sec REAL,
      end_sec REAL,
      notes TEXT,
      created_at TEXT NOT NULL,
      server_id INTEGER,
      synced_at TEXT
    );
    INSERT INTO context_events_rebuilt
      (uuid, capture_uuid, label_uuid, key, start_sec, end_sec, notes,
       created_at, server_id, synced_at)
    SELECT uuid, capture_uuid, label_uuid, key, start_sec, end_sec, notes,
           created_at, server_id, synced_at
      FROM context_events;
    DROP TABLE context_events;
    ALTER TABLE context_events_rebuilt RENAME TO context_events;
    CREATE INDEX IF NOT EXISTS context_capture ON context_events (capture_uuid);
    CREATE INDEX IF NOT EXISTS context_label ON context_events (label_uuid);
    `,
  ),
  addColumn(
    "captures",
    "region",
    // "Utah, US". Nullable because every capture that already exists predates
    // the question, and inventing a region for one recorded a year ago would be
    // a guess written into the corpus as a fact.
    "TEXT",
  ),
  sql(
    "fold exact_private into exact + censor",
    // The pre-split location setting meant "record them, never show them" —
    // exact + censor once those became separate questions. Every reader used
    // to tolerate the stored value at run time, forever, because nothing ever
    // rewrote it; this rewrites it once, which is what lets the tolerance be
    // deleted instead of maintained. Rewritten in the censoring direction, so
    // the one way this setting must never fail — open — stays closed even for
    // a phone that skipped every build since July.
    //
    // app_state may not exist yet: SettingsStore creates it on first open,
    // and a fresh install runs migrations before that. Created here with the
    // same shape so the UPDATE always has a table to look at.
    `
    CREATE TABLE IF NOT EXISTS app_state (
      key TEXT PRIMARY KEY NOT NULL,
      value TEXT NOT NULL
    );
    UPDATE app_state
       SET value = json_set(value, '$.locationPrecision', 'exact',
                                   '$.censorCoords', json('true'))
     WHERE key = 'settings'
       AND json_extract(value, '$.locationPrecision') = 'exact_private';
    `,
  ),
];
