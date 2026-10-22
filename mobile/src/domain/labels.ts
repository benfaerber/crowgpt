/**
 * Human ground truth, made in the field.
 *
 * Stored locally first like everything else here: a label is most accurate the
 * moment the bird is still in view, which is exactly when there is least likely
 * to be signal. It reaches the server on the next sync.
 *
 * A label is a *span*, not a whole capture. A two-minute recording with one
 * rattle in it is mostly not-rattle, and training on the whole clip teaches the
 * model that everything around the rattle is also a rattle.
 */
export interface LabelRecord {
  /** Idempotency key — a retried push edits rather than duplicates. */
  uuid: string;
  captureUuid: string;
  /** A key from the served vocabulary (`FleetConfig.labels`). */
  callType: string;
  species: string;
  startSec: number;
  endSec: number;
  /**
   * The vocabulary version on screen when this was decided.
   *
   * Stored locally rather than stamped at push time: a label made in a park on
   * Tuesday and synced on Friday was chosen from Tuesday's list, and by Friday
   * the phone may hold a different one.
   */
  configVersion?: number;
  /**
   * Set when this label confirms or corrects a model detection, rather than
   * being drawn from scratch. Worth keeping: agreement rates are how you find
   * out whether the model is getting better.
   */
  fromDetection?: boolean;
  /**
   * Which bird the recordist watched make this call, as a key from
   * `FleetConfig.caller_roles`.
   *
   * Optional, and absent is a real answer meaning nobody looked — which must
   * stay distinct from "nobody was there". Experiment 0017 established the
   * audio does not carry the caller, so this is the one field on a label that
   * cannot be filled in afterwards by anyone: it is seen live or it is lost.
   */
  callerRole?: string;
  createdAt: string;
  serverId?: number;
  syncedAt?: string;
}

export type NewLabel = Omit<LabelRecord, "serverId" | "syncedAt">;

export const DEFAULT_SPECIES = "American Crow";

/** Labels the server has not accepted yet. */
export function isPendingSync(label: LabelRecord): boolean {
  return label.serverId === undefined;
}
