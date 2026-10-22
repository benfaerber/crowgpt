import type { NewSighting, SightingRecord } from "../domain/sightings";

export interface SightingRepository {
  add(sighting: NewSighting): Promise<SightingRecord>;
  forCapture(captureUuid: string): Promise<SightingRecord[]>;
  remove(uuid: string): Promise<void>;
  update(uuid: string, patch: Partial<SightingRecord>): Promise<SightingRecord>;
  pendingSync(): Promise<SightingRecord[]>;
  forgetServerState(): Promise<void>;
}
