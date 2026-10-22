import type { LabelRecord, NewLabel } from "../domain/labels";

/**
 * Where field labels live until they are pushed.
 *
 * Separate from the capture record rather than a column on it: there are many
 * labels per capture, they are spans, and they are made and retracted
 * independently of everything else about the recording.
 */
export interface LabelRepository {
  add(label: NewLabel): Promise<LabelRecord>;
  forCapture(captureUuid: string): Promise<LabelRecord[]>;
  remove(uuid: string): Promise<void>;
  update(uuid: string, patch: Partial<LabelRecord>): Promise<LabelRecord>;
  /**
   * Recent labels of one call type, across every capture on the phone.
   *
   * For comparing a call in hand against ones already decided — "this was
   * marked an alarm call and the new one sounds the same". Everything needed is
   * already local, so it works with no signal, which is where the question gets
   * asked.
   */
  byCallType(callType: string, limit?: number): Promise<LabelRecord[]>;
  /**
   * How many labels each capture has, in one query.
   *
   * One query rather than `forCapture` per row because the list asks this about
   * everything on the phone every time it renders, and a hundred round trips to
   * SQLite to draw one badge is how a list starts stuttering. Captures with no
   * labels are simply absent — the caller reads a missing key as zero, which is
   * what it means.
   */
  countsByCapture(): Promise<Map<string, number>>;
  /** Everything the server has not accepted yet, oldest first. */
  pendingSync(): Promise<LabelRecord[]>;
  /** Drop remembered server ids — the server they belonged to has changed. */
  forgetServerState(): Promise<void>;
}

export class LabelNotFound extends Error {
  constructor(uuid: string) {
    super(`no label ${uuid}`);
    this.name = "LabelNotFound";
  }
}
