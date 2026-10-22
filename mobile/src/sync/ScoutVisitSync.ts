/**
 * Push scout visits to the field server — the LogSync shape, on purpose.
 *
 * Standalone rather than part of SyncEngine for LogSync's reason: sync is
 * about the corpus, and a scouting mark must never fail a run that carried a
 * field recording. Returns an outcome instead of throwing; a failed push
 * leaves rows pending and the next call retries them.
 */

import type { ScoutVisitRepository } from "../data/ScoutVisitRepository";
import type { FieldServerClient } from "../net/FieldServerClient";

const BATCH = 50;

export class ScoutVisitSync {
  constructor(
    private readonly visits: ScoutVisitRepository,
    private readonly client: () => FieldServerClient,
  ) {}

  async run(): Promise<{ sent: number; error?: string }> {
    let sent = 0;
    try {
      const pending = await this.visits.pendingSync(BATCH);
      for (const visit of pending) {
        const created = await this.client().addScoutVisit(visit);
        await this.visits.markSynced(
          visit.uuid, created.id, new Date().toISOString());
        sent += 1;
      }
      return { sent };
    } catch (error) {
      return { sent, error: error instanceof Error ? error.message : String(error) };
    }
  }
}
