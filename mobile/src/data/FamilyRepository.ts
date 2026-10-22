import type { FamilyRecord } from "../domain/families";

export interface FamilyRepository {
  add(family: Omit<FamilyRecord, "serverId" | "syncedAt">): Promise<FamilyRecord>;
  get(uuid: string): Promise<FamilyRecord | null>;
  list(): Promise<FamilyRecord[]>;
  update(uuid: string, patch: Partial<FamilyRecord>): Promise<FamilyRecord>;
  /** Families the server has not seen yet — pushed before any capture referencing them. */
  pendingSync(): Promise<FamilyRecord[]>;
  remove(uuid: string): Promise<void>;
}
