import type { SightingRepository } from "./SightingRepository";
import { isPendingSync, type NewSighting, type SightingRecord } from "../domain/sightings";

/** In-memory store, for host-side tests. Same contract as the SQLite one. */
export class MemorySightingRepository implements SightingRepository {
  private readonly sightings = new Map<string, SightingRecord>();

  async add(sighting: NewSighting): Promise<SightingRecord> {
    this.sightings.set(sighting.uuid, { ...sighting });
    return { ...sighting };
  }

  async forCapture(captureUuid: string): Promise<SightingRecord[]> {
    return [...this.sightings.values()]
      .filter((s) => s.captureUuid === captureUuid)
      .sort((a, b) => a.offsetSec - b.offsetSec)
      .map((s) => ({ ...s }));
  }

  async remove(uuid: string): Promise<void> {
    this.sightings.delete(uuid);
  }

  async update(uuid: string, patch: Partial<SightingRecord>): Promise<SightingRecord> {
    const existing = this.sightings.get(uuid);
    if (!existing) throw new Error(`no sighting ${uuid}`);
    const updated = { ...existing, ...patch };
    this.sightings.set(uuid, updated);
    return { ...updated };
  }

  async pendingSync(): Promise<SightingRecord[]> {
    return [...this.sightings.values()]
      .filter(isPendingSync)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((s) => ({ ...s }));
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, s] of this.sightings) {
      this.sightings.set(uuid, { ...s, serverId: undefined, syncedAt: undefined });
    }
  }
}
