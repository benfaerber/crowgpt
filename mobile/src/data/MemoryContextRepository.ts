import type { ContextRepository } from "./ContextRepository";
import { isPendingSync, type ContextRecord, type NewContext } from "../domain/context";

/** In-memory store, for host-side tests. Same contract as the SQLite one. */
export class MemoryContextRepository implements ContextRepository {
  private readonly events = new Map<string, ContextRecord>();

  async add(event: NewContext): Promise<ContextRecord> {
    this.events.set(event.uuid, { ...event });
    return { ...event };
  }

  async forCapture(captureUuid: string): Promise<ContextRecord[]> {
    return [...this.events.values()]
      .filter((event) => event.captureUuid === captureUuid)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((event) => ({ ...event }));
  }

  async forLabel(labelUuid: string): Promise<ContextRecord[]> {
    return [...this.events.values()]
      .filter((event) => event.labelUuid === labelUuid)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((event) => ({ ...event }));
  }

  async remove(uuid: string): Promise<void> {
    this.events.delete(uuid);
  }

  async update(uuid: string, patch: Partial<ContextRecord>): Promise<ContextRecord> {
    const existing = this.events.get(uuid);
    if (!existing) throw new Error(`no context event ${uuid}`);
    const updated = { ...existing, ...patch };
    this.events.set(uuid, updated);
    return { ...updated };
  }

  async pendingSync(): Promise<ContextRecord[]> {
    return [...this.events.values()]
      .filter(isPendingSync)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((event) => ({ ...event }));
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, event] of this.events) {
      this.events.set(uuid, { ...event, serverId: undefined, syncedAt: undefined });
    }
  }
}
