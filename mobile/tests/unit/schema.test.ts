import { describe, expect, it } from "vitest";

import { MIGRATIONS } from "../../src/data/schema";
import { SQLiteDatabase } from "../support/expoSqliteShim";

/**
 * The phone's migration ledger.
 *
 * `user_version` identifies steps by *position*, so inserting one in the middle
 * re-runs everything after it against a database that already applied them.
 * These make that mistake loud — there is no runtime check for it, because by
 * the time it would run the damage is done.
 */
describe("schema migrations", () => {
  it("starts with the context_events rebuild", () => {
    // Position 0 forever. A phone that has run it recorded user_version = 1;
    // inserting anything before it would re-run this against a rebuilt table.
    expect(MIGRATIONS[0].name).toBe("context_events.label_uuid may be null");
  });

  it("names every step uniquely, so the log can be read", () => {
    const names = MIGRATIONS.map((m) => m.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("every step can actually run", () => {
    expect(MIGRATIONS.every((m) => typeof m.up === "function")).toBe(true);
  });
});

describe("folding exact_private into exact + censor", () => {
  const fold = MIGRATIONS.find(
    (m) => m.name === "fold exact_private into exact + censor",
  )!;

  const settings = async (db: SQLiteDatabase) => {
    const row = await db.getFirstAsync<{ value: string }>(
      "SELECT value FROM app_state WHERE key = 'settings'",
    );
    return JSON.parse(row!.value);
  };

  const seeded = async (stored: object) => {
    const db = new SQLiteDatabase();
    await db.execAsync(
      "CREATE TABLE app_state (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);",
    );
    await db.runAsync("INSERT INTO app_state (key, value) VALUES (?, ?)", [
      "settings",
      JSON.stringify(stored),
    ]);
    return db;
  };

  it("rewrites the pre-split value in the censoring direction", async () => {
    // "Record them, never show them" — the fold must keep both halves true.
    const db = await seeded({
      locationPrecision: "exact_private",
      homeRegion: "Utah, US",
    });
    await fold.up(db);
    const after = await settings(db);
    expect(after.locationPrecision).toBe("exact");
    expect(after.censorCoords).toBe(true);
    expect(after.homeRegion).toBe("Utah, US");
  });

  it("leaves a phone that already chose leave-alone alone", async () => {
    // censorCoords: false is a deliberate post-split choice; the fold must
    // never flip it for someone who was never on the old value.
    const db = await seeded({ locationPrecision: "exact", censorCoords: false });
    await fold.up(db);
    const after = await settings(db);
    expect(after.locationPrecision).toBe("exact");
    expect(after.censorCoords).toBe(false);
  });

  it("runs on a fresh install where app_state does not exist yet", async () => {
    const db = new SQLiteDatabase();
    await expect(fold.up(db)).resolves.not.toThrow();
  });
});
