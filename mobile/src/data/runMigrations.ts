import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import { migrate } from "./migrations";
import { MIGRATIONS } from "./schema";

/**
 * Bring the phone's store up to date. Safe to call on every launch.
 *
 * Separate from `schema.ts` only because that list is imported by the host test
 * run, and this file opens a real database.
 *
 * Returns the names of anything it ran, so a launch that reshaped the database
 * says so rather than doing it invisibly.
 */
export async function runMigrations(name = "cawtalker.db"): Promise<string[]> {
  const db = await openStore(name);
  return migrate(db, MIGRATIONS);
}
