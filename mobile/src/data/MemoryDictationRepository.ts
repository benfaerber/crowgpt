import { DictationNotFound, type DictationRepository } from "./DictationRepository";
import { isPendingSync, type DictationRecord, type NewDictation } from "../domain/dictations";

/** In-memory store, for host-side tests. Same contract as the SQLite one. */
export class MemoryDictationRepository implements DictationRepository {
  private readonly rows = new Map<string, DictationRecord>();

  async add(dictation: NewDictation): Promise<DictationRecord> {
    const record: DictationRecord = { ...dictation, uploadedBytes: 0 };
    this.rows.set(record.uuid, record);
    return { ...record };
  }

  async get(uuid: string): Promise<DictationRecord | null> {
    const found = this.rows.get(uuid);
    return found ? { ...found } : null;
  }

  async forCapture(captureUuid: string): Promise<DictationRecord[]> {
    return this.byRecordedAt((d) => d.captureUuid === captureUuid);
  }

  async forCaptures(captureUuids: readonly string[]): Promise<DictationRecord[]> {
    const wanted = new Set(captureUuids);
    return this.byRecordedAt((d) => wanted.has(d.captureUuid));
  }

  async pendingSync(): Promise<DictationRecord[]> {
    return this.byRecordedAt(isPendingSync);
  }

  async stale(): Promise<DictationRecord[]> {
    return this.byRecordedAt((d) => d.state === "recording");
  }

  async update(uuid: string, patch: Partial<DictationRecord>): Promise<DictationRecord> {
    const found = this.rows.get(uuid);
    if (!found) throw new DictationNotFound(uuid);
    const updated = { ...found, ...patch };
    this.rows.set(uuid, updated);
    return { ...updated };
  }

  async remove(uuid: string): Promise<void> {
    this.rows.delete(uuid);
  }

  async audioPaths(): Promise<string[]> {
    return [...this.rows.values()].map((d) => d.audioPath);
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, row] of this.rows) {
      this.rows.set(uuid, {
        ...row, serverId: undefined, uploadedBytes: 0, syncedAt: undefined,
      });
    }
  }

  private byRecordedAt(keep: (d: DictationRecord) => boolean): DictationRecord[] {
    return [...this.rows.values()]
      .filter(keep)
      .sort((a, b) => a.recordedAt.localeCompare(b.recordedAt))
      .map((d) => ({ ...d }));
  }
}
