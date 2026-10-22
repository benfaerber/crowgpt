import { LabelNotFound, type LabelRepository } from "./LabelRepository";
import { isPendingSync, type LabelRecord, type NewLabel } from "../domain/labels";

/** In-memory store, for host-side tests. Same contract as the SQLite one. */
export class MemoryLabelRepository implements LabelRepository {
  private readonly labels = new Map<string, LabelRecord>();

  async add(label: NewLabel): Promise<LabelRecord> {
    const record: LabelRecord = { ...label };
    this.labels.set(record.uuid, record);
    return { ...record };
  }

  async forCapture(captureUuid: string): Promise<LabelRecord[]> {
    return [...this.labels.values()]
      .filter((label) => label.captureUuid === captureUuid)
      .sort((a, b) => a.startSec - b.startSec)
      .map((label) => ({ ...label }));
  }

  async countsByCapture(): Promise<Map<string, number>> {
    const counts = new Map<string, number>();
    for (const label of this.labels.values()) {
      counts.set(label.captureUuid, (counts.get(label.captureUuid) ?? 0) + 1);
    }
    return counts;
  }

  async remove(uuid: string): Promise<void> {
    this.labels.delete(uuid);
  }

  async update(uuid: string, patch: Partial<LabelRecord>): Promise<LabelRecord> {
    const existing = this.labels.get(uuid);
    if (!existing) throw new LabelNotFound(uuid);
    const updated = { ...existing, ...patch };
    this.labels.set(uuid, updated);
    return { ...updated };
  }

  async byCallType(callType: string, limit = 5): Promise<LabelRecord[]> {
    return [...this.labels.values()]
      .filter((label) => label.callType === callType)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, limit)
      .map((label) => ({ ...label }));
  }

  async pendingSync(): Promise<LabelRecord[]> {
    return [...this.labels.values()]
      .filter(isPendingSync)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((label) => ({ ...label }));
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, label] of this.labels) {
      this.labels.set(uuid, { ...label, serverId: undefined, syncedAt: undefined });
    }
  }
}
