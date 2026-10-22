import * as SQLite from "expo-sqlite";

import { openStore } from "./openStore";

import type { ScoutLayer } from "../domain/scout";
import type { TreeLayer } from "../domain/trees";
import type { FleetConfig } from "../domain/config";
import type { Identity } from "../domain/identity";

/**
 * Small key/value store for things that must outlive the process but aren't
 * captures — the fleet settings and, critically, the device's bearer token.
 *
 * The token has to persist. Enrollment mints a *device identity*, and the field
 * server scopes capture `client_uuid`s per device: if the app re-enrolled on
 * every launch it would get a fresh device row each time, and an unsynced
 * capture retried after a restart would land as a duplicate under the new
 * device instead of resolving to the original. Persisting it is what keeps the
 * idempotency guarantee true across restarts, not just within one session.
 */
export interface PersistedState<TSettings> {
  settings?: TSettings;
  deviceToken?: string;
  /**
   * Who the server says this device belongs to. Cached so Settings can answer
   * "whose captures are these?" with no network — the app is offline-first
   * everywhere else and identity shouldn't be the exception.
   */
  identity?: Identity;
  /**
   * The last vocabulary the server served.
   *
   * Cached because labelling has to work with no signal — that is when a
   * recordist is most likely to be doing it, and an empty label set in a field
   * is worse than a slightly stale one.
   */
  config?: FleetConfig;
  /** The tall-trees scouting layer, cached for the same no-signal reason. */
  trees?: TreeLayer;
  /** 0084's ranked scouting targets, ditto. */
  scout?: ScoutLayer;
}

export interface SettingsStore<TSettings> {
  load(): Promise<PersistedState<TSettings>>;
  saveSettings(settings: TSettings): Promise<void>;
  saveDeviceToken(token: string | undefined): Promise<void>;
  saveIdentity(identity: Identity | undefined): Promise<void>;
  saveConfig(config: FleetConfig): Promise<void>;
  saveTrees(trees: TreeLayer): Promise<void>;
  saveScout(scout: ScoutLayer): Promise<void>;
}

export class SqliteSettingsStore<TSettings> implements SettingsStore<TSettings> {
  private constructor(private readonly db: SQLite.SQLiteDatabase) {}

  static async open<TSettings>(name = "cawtalker.db"): Promise<SqliteSettingsStore<TSettings>> {
    const db = await openStore(name);
    await db.execAsync(`
      CREATE TABLE IF NOT EXISTS app_state (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
      );
    `);
    return new SqliteSettingsStore<TSettings>(db);
  }

  async load(): Promise<PersistedState<TSettings>> {
    const rows = await this.db.getAllAsync<{ key: string; value: string }>(
      "SELECT key, value FROM app_state",
    );
    const state: PersistedState<TSettings> = {};
    for (const row of rows) {
      if (row.key === "settings") state.settings = JSON.parse(row.value) as TSettings;
      if (row.key === "device_token") state.deviceToken = row.value;
      if (row.key === "identity") state.identity = JSON.parse(row.value) as Identity;
      if (row.key === "config") state.config = JSON.parse(row.value) as FleetConfig;
      if (row.key === "trees") state.trees = JSON.parse(row.value) as TreeLayer;
      if (row.key === "scout") state.scout = JSON.parse(row.value) as ScoutLayer;
    }
    return state;
  }

  saveSettings(settings: TSettings): Promise<void> {
    return this.put("settings", JSON.stringify(settings));
  }

  async saveDeviceToken(token: string | undefined): Promise<void> {
    if (token === undefined) {
      await this.db.runAsync("DELETE FROM app_state WHERE key = 'device_token'");
      return;
    }
    await this.put("device_token", token);
  }

  async saveIdentity(identity: Identity | undefined): Promise<void> {
    if (identity === undefined) {
      await this.db.runAsync("DELETE FROM app_state WHERE key = 'identity'");
      return;
    }
    await this.put("identity", JSON.stringify(identity));
  }

  saveConfig(config: FleetConfig): Promise<void> {
    return this.put("config", JSON.stringify(config));
  }

  saveTrees(trees: TreeLayer): Promise<void> {
    return this.put("trees", JSON.stringify(trees));
  }

  saveScout(scout: ScoutLayer): Promise<void> {
    return this.put("scout", JSON.stringify(scout));
  }

  private async put(key: string, value: string): Promise<void> {
    await this.db.runAsync(
      "INSERT INTO app_state (key, value) VALUES (?, ?) " +
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      [key, value],
    );
  }
}
