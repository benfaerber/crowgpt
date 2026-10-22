import type { FamilyRecord } from "../domain/families";
import type { FamilyRepository } from "./FamilyRepository";

/**
 * In-memory families. Kept apart from the SQLite one on purpose: the host
 * tests import this, and a native import anywhere in the file would pull
 * expo-sqlite into Node, where it cannot load.
 */
export class MemoryFamilyRepository implements FamilyRepository {
  private readonly families = new Map<string, FamilyRecord>();

  async add(family: Omit<FamilyRecord, "serverId" | "syncedAt">): Promise<FamilyRecord> {
    const record: FamilyRecord = { ...family };
    this.families.set(record.uuid, record);
    return { ...record };
  }
  async get(uuid: string) {
    const found = this.families.get(uuid);
    return found ? { ...found } : null;
  }
  async list() {
    return [...this.families.values()].sort((a, b) => a.name.localeCompare(b.name));
  }
  async pendingSync() {
    // Mirrors the sqlite rule: unsynced OR edited (synced_at cleared).
    return [...this.families.values()].filter((f) => f.syncedAt === undefined);
  }
  async update(uuid: string, patch: Partial<FamilyRecord>) {
    const updated = { ...this.families.get(uuid)!, ...patch };
    this.families.set(uuid, updated);
    return { ...updated };
  }
  async remove(uuid: string) {
    this.families.delete(uuid);
  }
}
