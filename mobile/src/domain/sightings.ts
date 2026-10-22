/**
 * Something seen near a recording, but not during it.
 *
 * The case this exists for: a crow gives an alarm bout, and five minutes later
 * a block away two hawks come into view. Worth writing down — it is the start
 * of a real hypothesis — but it is emphatically not what a {@link ContextRecord}
 * is.
 *
 * Context is ground truth: you watched a dog walk through at 0:30 and tagged
 * the calls in that window. It is what the calls × context matrix is built
 * from. Putting an after-the-fact sighting in there would be circular in the
 * worst way — you infer "that was an alarm" from the hawk, tag the hawk, and
 * the matrix then reports that alarm calls co-occur with hawks. True by
 * construction, and a year later indistinguishable from a result you earned.
 *
 * So this is its own record with its own table, not a flag on that one.
 * Separation by construction rather than by discipline.
 *
 * The vocabulary is the *same* one context uses, deliberately: it is what lets
 * "how often does an alarm bout precede a raptor appearing" eventually be
 * answered from data instead of from the tag you already applied.
 */
export interface SightingRecord {
  uuid: string;
  captureUuid: string;
  /** A key from the served context vocabulary. */
  key: string;
  /**
   * Seconds relative to the start of the recording — negative before it,
   * positive after.
   *
   * Required, and the whole point. A sighting with no time on it is just a
   * context event with the honesty taken out, so there is no way to write one.
   */
  offsetSec: number;
  /**
   * Roughly how far away, in metres. Optional and expected to be a guess:
   * "about a block" is a real answer, and demanding precision would only
   * produce invented precision.
   */
  distanceM?: number;
  notes?: string;
  createdAt: string;
  serverId?: number;
  syncedAt?: string;
}

export type NewSighting = Omit<SightingRecord, "serverId" | "syncedAt">;

export function isPendingSync(sighting: SightingRecord): boolean {
  return sighting.serverId === undefined;
}

/** "5m after the recording", "1m30s before" — how it reads on the capture. */
export function describeOffset(offsetSec: number): string {
  if (offsetSec === 0) return "as it ended";
  const magnitude = Math.abs(offsetSec);
  const minutes = Math.floor(magnitude / 60);
  const seconds = Math.round(magnitude % 60);
  const span =
    minutes > 0
      ? seconds > 0
        ? `${minutes}m ${seconds}s`
        : `${minutes}m`
      : `${seconds}s`;
  return `${span} ${offsetSec > 0 ? "after" : "before"}`;
}
