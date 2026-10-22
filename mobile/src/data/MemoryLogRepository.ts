import type { LogRepository } from "./LogRepository";
import { LEVELS, type LogEntry, type LogLevel, type StoredLogEntry } from "../domain/logging";

/** In-memory store, for host-side tests. Same contract as the SQLite one. */
export class MemoryLogRepository implements LogRepository {
  private readonly entries: StoredLogEntry[] = [];

  /** Set to make the store fail, which is a case the logger has to survive. */
  failing = false;

  async append(entries: LogEntry[]): Promise<void> {
    if (this.failing) throw new Error("log store unavailable");
    for (const entry of entries) {
      if (this.entries.some((held) => held.uuid === entry.uuid)) continue;
      this.entries.push({ ...entry });
    }
  }

  async recent({
    limit = 300,
    level,
    tag,
  }: { limit?: number; level?: LogLevel; tag?: string } = {}): Promise<StoredLogEntry[]> {
    return this.entries
      .filter((entry) => !level || LEVELS.indexOf(entry.level) >= LEVELS.indexOf(level))
      .filter((entry) => !tag || entry.tag === tag)
      .slice()
      .reverse()
      .slice(0, limit)
      .map((entry) => ({ ...entry }));
  }

  async pendingSync(limit = 500): Promise<StoredLogEntry[]> {
    return this.entries
      .filter((entry) => entry.syncedAt === undefined)
      .slice(0, limit)
      .map((entry) => ({ ...entry }));
  }

  async markSynced(uuids: string[]): Promise<void> {
    const wanted = new Set(uuids);
    for (const entry of this.entries) {
      if (wanted.has(entry.uuid)) entry.syncedAt = new Date().toISOString();
    }
  }

  async countPending(): Promise<number> {
    return this.entries.filter((entry) => entry.syncedAt === undefined).length;
  }

  async clear(): Promise<void> {
    this.entries.length = 0;
  }

  async tags(): Promise<string[]> {
    return [...new Set(this.entries.map((entry) => entry.tag))].sort();
  }

  get all(): StoredLogEntry[] {
    return this.entries.map((entry) => ({ ...entry }));
  }
}
