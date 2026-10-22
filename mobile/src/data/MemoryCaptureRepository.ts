import { CaptureNotFound, type CaptureRepository } from "./CaptureRepository";
import { isDirtyingChange } from "../domain/revision";
import { isPendingSync, type CaptureRecord, type NewCapture } from "../domain/types";

/**
 * In-memory store. Used by the host-side tests, and by the app until the
 * SQLite adapter lands — it satisfies the same contract, so nothing above it
 * changes when the real one arrives.
 */
export class MemoryCaptureRepository implements CaptureRepository {
  private readonly captures = new Map<string, CaptureRecord>();

  async add(capture: NewCapture): Promise<CaptureRecord> {
    const record: CaptureRecord = {
      ...capture,
      syncState: "local",
      uploadedBytes: 0,
      attempts: 0,
      keep: capture.keep ?? false,
    };
    this.captures.set(record.uuid, record);
    return { ...record };
  }

  async get(uuid: string): Promise<CaptureRecord | null> {
    const found = this.captures.get(uuid);
    return found ? { ...found } : null;
  }

  async list(): Promise<CaptureRecord[]> {
    return [...this.captures.values()]
      // Parts of a merge are not listed. Same rule as the SQLite repository,
      // and the reason the two are tested against one contract.
      .filter((c) => c.mergedInto === undefined)
      .sort((a, b) => b.recordedAt.localeCompare(a.recordedAt))
      .map((c) => ({ ...c }));
  }

  /** Merge parts included, unlike list() — see the interface. */
  async audioPaths(): Promise<string[]> {
    return [...this.captures.values()]
      .map((c) => c.audioPath)
      .filter((path): path is string => !!path);
  }

  async pendingSync(): Promise<CaptureRecord[]> {
    return [...this.captures.values()]
      .filter(isPendingSync)
      .sort((a, b) => a.recordedAt.localeCompare(b.recordedAt))
      .map((c) => ({ ...c }));
  }

  async update(uuid: string, patch: Partial<CaptureRecord>): Promise<CaptureRecord> {
    const existing = this.captures.get(uuid);
    if (!existing) throw new CaptureNotFound(uuid);
    const updated = { ...existing, ...patch };
    // Mirrors the SQLite store: an edit to anything the server holds bumps the
    // revision, which is what makes it eligible for another push.
    if (patch.localRevision === undefined && isDirtyingChange(existing, patch)) {
      updated.localRevision = (existing.localRevision ?? 0) + 1;
    }
    this.captures.set(uuid, updated);
    return { ...updated };
  }

  async remove(uuid: string): Promise<void> {
    // Deleting a merged capture un-merges it: otherwise its parts keep pointing
    // at a row that is gone, stay out of list(), and cannot be brought back.
    for (const [key, capture] of this.captures) {
      if (capture.mergedInto === uuid) {
        this.captures.set(key, { ...capture, mergedInto: undefined });
      }
    }
    this.captures.delete(uuid);
  }

  async recoverInterrupted(): Promise<number> {
    let recovered = 0;
    for (const [uuid, capture] of this.captures) {
      if (capture.syncState !== "syncing") continue;
      this.captures.set(uuid, {
        ...capture,
        syncState: "failed",
        lastError: "interrupted — the sync stopped before this capture finished",
      });
      recovered += 1;
    }
    return recovered;
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, capture] of this.captures) {
      this.captures.set(uuid, {
        ...capture,
        syncState: "local",
        serverCaptureId: undefined,
        serverMediaId: undefined,
        uploadedBytes: 0,
        syncedAt: undefined,
        lastError: undefined,
      });
    }
  }
}
