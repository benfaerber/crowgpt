import type { DictationRecord, NewDictation } from "../domain/dictations";

/**
 * Where spoken notes live until they are pushed.
 *
 * Its own table rather than columns on the capture, which is what video got.
 * Five columns per extra file admits exactly one, and one is wrong here: a first
 * impression and a correction thirty seconds later are different observations at
 * different moments, and flattening the second onto the first destroys the more
 * valuable one. It also makes "which notes are unsent" a query rather than a
 * scan of every capture row.
 */
export interface DictationRepository {
  add(dictation: NewDictation): Promise<DictationRecord>;
  get(uuid: string): Promise<DictationRecord | null>;
  forCapture(captureUuid: string): Promise<DictationRecord[]>;
  /**
   * Notes on any of these captures, newest last.
   *
   * Takes a list because of merges: a capture folded into another is never
   * pushed again, so a note recorded against a take that later became part of a
   * bout would be stranded on the phone forever with nothing saying so. The
   * pusher asks for the merge and its parts together.
   */
  forCaptures(captureUuids: readonly string[]): Promise<DictationRecord[]>;
  /** Everything the server has not got all of yet. */
  pendingSync(): Promise<DictationRecord[]>;
  /** Rows a killed process left mid-recording, for the launch-time reconcile. */
  stale(): Promise<DictationRecord[]>;
  update(uuid: string, patch: Partial<DictationRecord>): Promise<DictationRecord>;
  remove(uuid: string): Promise<void>;
  /** Every audio path held, so the orphan sweep does not claim one as a capture. */
  audioPaths(): Promise<string[]>;
  /** Drop remembered server ids — the server they belonged to has changed. */
  forgetServerState(): Promise<void>;
}

export class DictationNotFound extends Error {
  constructor(uuid: string) {
    super(`no dictation ${uuid}`);
    this.name = "DictationNotFound";
  }
}
