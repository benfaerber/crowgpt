import type { LogEntry, LogLevel, StoredLogEntry } from "../domain/logging";

/**
 * Where log lines live between being written and being read.
 *
 * `append` takes a batch rather than one entry because that is how they arrive
 * — the logger buffers and flushes, so that the recorder never waits on a
 * write. See app/Log.ts.
 */
export interface LogRepository {
  append(entries: LogEntry[]): Promise<void>;
  /** Newest first. */
  recent(options?: { limit?: number; level?: LogLevel; tag?: string }): Promise<StoredLogEntry[]>;
  /** Oldest first — the order they should be pushed in. */
  pendingSync(limit?: number): Promise<StoredLogEntry[]>;
  markSynced(uuids: string[]): Promise<void>;
  countPending(): Promise<number>;
  clear(): Promise<void>;
  tags(): Promise<string[]>;
}
