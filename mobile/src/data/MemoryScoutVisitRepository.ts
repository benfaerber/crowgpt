import type { ScoutVisitRepository } from "./ScoutVisitRepository";
import type { ScoutVisit } from "../domain/scoutVisits";

export class MemoryScoutVisitRepository implements ScoutVisitRepository {
  private readonly visits = new Map<string, ScoutVisit>();

  async add(visit: ScoutVisit): Promise<void> {
    if (!this.visits.has(visit.uuid)) {
      this.visits.set(visit.uuid, { ...visit });
    }
  }

  async all(): Promise<ScoutVisit[]> {
    return [...this.visits.values()].sort(
      (a, b) => a.visitedAt.localeCompare(b.visitedAt));
  }

  async pendingSync(limit: number): Promise<ScoutVisit[]> {
    return (await this.all())
      .filter((v) => v.serverId === undefined)
      .slice(0, limit);
  }

  async markSynced(uuid: string, serverId: number, syncedAt: string): Promise<void> {
    const visit = this.visits.get(uuid);
    if (visit) {
      this.visits.set(uuid, { ...visit, serverId, syncedAt });
    }
  }

  async forgetServerState(): Promise<void> {
    for (const [uuid, visit] of this.visits) {
      this.visits.set(uuid,
        { ...visit, serverId: undefined, syncedAt: undefined });
    }
  }
}
