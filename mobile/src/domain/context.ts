/**
 * What was happening in the world when the bird called.
 *
 * The other half of the semantics problem. A label records what the crow
 * *said*; this records what a human *witnessed*. Neither is interesting alone —
 * calls without context are a phonetics dataset, context without calls is a
 * diary — and only the pairing can turn "this is an alarm call" into "this is
 * what a crow says about a dog".
 *
 * Tagged in the moment, because it is the one thing that genuinely cannot be
 * recovered later. You can re-listen to a recording a year from now and still
 * label the call; you cannot go back and see whether there was a dog.
 *
 * Attached to a *call*, not a capture. A two-minute recording might have a dog
 * appear at 0:30 and leave at 0:50 — the alarm calls in that window are about
 * the dog, the song at 1:40 is not. Tagging the capture would credit every
 * situation to every call in it and report that crows sing at dogs.
 */
export interface ContextRecord {
  uuid: string;
  captureUuid: string;
  /**
   * The call this was the situation for.
   *
   * Absent only on a capture confirmed to hold no calls. The rule that context
   * hangs off a call exists so one situation cannot be credited to every call
   * in a recording — with zero calls there is nothing to miscredit, and this is
   * the only way to record "peanuts down, three crows watching, nobody said
   * anything". That row is the control group every co-occurrence number needs.
   */
  labelUuid?: string;
  /** A key from the served context vocabulary. */
  key: string;
  /** The call's span, copied so the event still says when it happened. */
  startSec?: number;
  endSec?: number;
  notes?: string;
  /** The vocabulary version on screen when this was witnessed. See labels.ts. */
  configVersion?: number;
  createdAt: string;
  serverId?: number;
  syncedAt?: string;
}

export type NewContext = Omit<ContextRecord, "serverId" | "syncedAt">;

export function isPendingSync(event: ContextRecord): boolean {
  return event.serverId === undefined;
}
