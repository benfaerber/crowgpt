/**
 * A spoken field note, recorded against a capture.
 *
 * The recordist talking, not the birds — and the distinction has to survive
 * every layer, because a human voice track counted as field audio is a worse
 * version of the problem the ★ Keep flag already holds back. Nothing here is
 * ever a capture, never reaches the analyzer, and never lands in a species or
 * call-type total.
 *
 * Why this exists at all: labelling is the bottleneck everything else waits on,
 * and the `label-set` skill's every fact comes from Ben's answers — recalled
 * hours later at a desk. A memo is the same answers taken in the field, seconds
 * after the birds did the thing.
 */

/** How long a recording has to be before it is worth keeping at all. */
export const MIN_DICTATION_MS = 1_000;

/**
 * A closed WAV holding nothing but its header.
 *
 * The size a recording is when it never got a sample — which is what a killed
 * process leaves behind. Uploading one would look like a successful sync of an
 * empty note, and the server would dutifully transcribe silence.
 */
export const WAV_HEADER_BYTES = 44;

export interface DictationRecord {
  uuid: string;
  captureUuid: string;
  audioPath: string;
  /** When he spoke — after the event, and not the capture's own time. */
  recordedAt: string;
  durationMs: number;
  bytes: number;
  sampleRate: number;
  channels: number;
  inputDevice?: string;
  inputHonoured?: boolean;
  /**
   * Where this memo is in its own life, which is not its sync state.
   *
   * "recording" is written before the first byte and is how a process that died
   * holding the pen is recognised at the next launch — the row's own version of
   * the `.writing` marker a capture gets. "interrupted" is what a launch-time
   * reconcile turns a stale "recording" into, and it exists to be visible: a
   * silently missing memo is indistinguishable from one he forgot to record.
   */
  state: "recording" | "ready" | "interrupted";
  serverId?: number;
  /** What the server has confirmed receiving — where a resume starts. */
  uploadedBytes: number;
  syncedAt?: string;
  /**
   * The machine's reading of what was said.
   *
   * Filled by the sync's one downward step. Push-only exists so a stale server
   * copy cannot overwrite a field recording; a transcript is produced ON the
   * server from audio the phone already sent, so there is no phone version to
   * contradict — the same reason `PrefetchAnalysis` pulls the detections.
   */
  transcript?: string;
  transcriptAt?: string;
}

export type NewDictation = Omit<
  DictationRecord,
  "serverId" | "uploadedBytes" | "syncedAt" | "transcript" | "transcriptAt"
>;

/** Everything the server has not got all of yet. */
export function isPendingSync(dictation: DictationRecord): boolean {
  if (dictation.state !== "ready") return false;
  return dictation.serverId === undefined || dictation.uploadedBytes < dictation.bytes;
}

/**
 * Whether this one may actually be sent.
 *
 * The guard against uploading a header. A process killed a moment after the
 * microphone opened leaves a 44-byte file and a row that says "recording"; both
 * checks are here rather than one, because a file can also be short for honest
 * reasons — a slipped thumb — and neither is worth a transcription job or the
 * "note" it would appear as afterwards.
 */
export function isPushable(dictation: DictationRecord): boolean {
  if (!isPendingSync(dictation)) return false;
  return dictation.bytes > WAV_HEADER_BYTES
    && dictation.durationMs >= MIN_DICTATION_MS;
}

/**
 * What to call one on screen.
 *
 * An ordinal and a length, never an invented name. Nobody titles a voice memo
 * in a field, and a generated title is the thing `CaptureRecord.name` already
 * refuses to do: a row that says something the recordist did not say.
 */
export function dictationLabel(dictation: DictationRecord, index: number): string {
  const seconds = Math.round(dictation.durationMs / 1000);
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return `Note ${index + 1} · ${clock}`;
}

/**
 * The one line that says where a memo has got to.
 *
 * Deliberately says "waiting to send" rather than nothing for the ordinary
 * case: this app is push-only and manual, so a note that has not left the phone
 * is the normal state and hiding it is how a recordist assumes it is safe.
 */
export function describeDictationState(dictation: DictationRecord): string {
  if (dictation.state === "recording") return "still recording";
  if (dictation.state === "interrupted") return "the app stopped while recording this";
  if (dictation.transcript) return "transcribed";
  if (dictation.syncedAt) return "sent — transcript arrives on the next sync";
  if (dictation.serverId !== undefined && dictation.uploadedBytes > 0) {
    const percent = Math.min(99, Math.round(
      (dictation.uploadedBytes / Math.max(1, dictation.bytes)) * 100));
    return `sending — ${percent}%`;
  }
  return "waiting to send";
}
