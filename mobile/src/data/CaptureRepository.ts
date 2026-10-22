import type { CaptureRecord, NewCapture } from "../domain/types";

/**
 * The local store contract.
 *
 * Everything above this line is storage-agnostic, so the SQLite implementation
 * is a thin adapter and the sync engine can be exercised on a host machine with
 * no device attached.
 */
export interface CaptureRepository {
  /** Persist a freshly recorded capture in the `local` state. */
  add(capture: NewCapture): Promise<CaptureRecord>;
  get(uuid: string): Promise<CaptureRecord | null>;
  /** Newest first — the order the capture list shows them in. */
  list(): Promise<CaptureRecord[]>;
  /** Captures in `local` or `failed`, oldest first, so a sync drains the backlog in order. */
  pendingSync(): Promise<CaptureRecord[]>;
  /**
   * Every audio path on record, merge parts included.
   *
   * Deliberately not `list()`, which hides parts: this answers "is any file on
   * disk unaccounted for", and a part recovered as a fresh capture would
   * resurrect audio the recordist folded away. See recoverAbandonedCaptures.
   */
  audioPaths(): Promise<string[]>;
  update(uuid: string, patch: Partial<CaptureRecord>): Promise<CaptureRecord>;
  remove(uuid: string): Promise<void>;
  /**
   * Drop every remembered server id and upload offset, returning all captures
   * to `local`. Used when the device's identity or server changes: ids minted
   * by one server mean nothing to another, and a capture pointing at a row it
   * can no longer reach would otherwise be stuck failing forever.
   */
  forgetServerState(): Promise<void>;
  /**
   * Put captures marked `syncing` back in the queue, and say how many.
   *
   * `syncing` is written when an upload starts, so a run that died leaves rows
   * claiming to be in flight — and `pendingSync` does not select them, so they
   * go quiet rather than retrying.
   */
  recoverInterrupted(): Promise<number>;
}

export class CaptureNotFound extends Error {
  constructor(uuid: string) {
    super(`no capture ${uuid}`);
    this.name = "CaptureNotFound";
  }
}
