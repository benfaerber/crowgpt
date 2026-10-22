import type { ScoutVisit } from "../domain/scoutVisits";

/** Held locally until pushed; the LogSync shape, not the per-capture one. */
export interface ScoutVisitRepository {
  add(visit: ScoutVisit): Promise<void>;
  all(): Promise<ScoutVisit[]>;
  /** Rows the server has not confirmed — no serverId yet. */
  pendingSync(limit: number): Promise<ScoutVisit[]>;
  markSynced(uuid: string, serverId: number, syncedAt: string): Promise<void>;
  /** The app points at a different server: every server id is now a lie. */
  forgetServerState(): Promise<void>;
}
