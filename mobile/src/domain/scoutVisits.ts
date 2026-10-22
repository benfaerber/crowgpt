/**
 * Scout visits — where the recordist actually went, and what was there.
 *
 * The 0084 scouting score is a prior graded by boots; these rows are the
 * boots. "nothing" is a first-class outcome, not an absence: a visited
 * target with no crows re-weights the score exactly as much as one with
 * them. Attached to no capture on purpose — a visit is about a place.
 */

export type VisitOutcome = "crows" | "nothing";
export type VisitKind = "tree" | "target" | "spot";

export interface ScoutVisit {
  uuid: string;
  kind: VisitKind;
  latitude: number;
  longitude: number;
  outcome: VisitOutcome;
  note?: string;
  /** The phone's clock at the moment of marking — the server keeps its own. */
  visitedAt: string;
  serverId?: number;
  syncedAt?: string;
}
