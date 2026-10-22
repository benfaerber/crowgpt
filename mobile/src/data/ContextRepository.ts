import type { ContextRecord, NewContext } from "../domain/context";

export interface ContextRepository {
  add(event: NewContext): Promise<ContextRecord>;
  forCapture(captureUuid: string): Promise<ContextRecord[]>;
  forLabel(labelUuid: string): Promise<ContextRecord[]>;
  remove(uuid: string): Promise<void>;
  update(uuid: string, patch: Partial<ContextRecord>): Promise<ContextRecord>;
  pendingSync(): Promise<ContextRecord[]>;
  forgetServerState(): Promise<void>;
}
