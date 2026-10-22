import type { PendingCapture } from "../domain/pendingCaptures";
import type { IdleSessionState } from "../recording/Recorder";

/**
 * What the rest of the app sees of the recorder.
 *
 * The shapes alone, so a component that renders one corner of the recorder
 * — the idle bar, the dictation card — can name its prop without importing
 * the hook that drives the microphone.
 */

export interface RecorderView {
  recording: boolean;
  /** The mic is open and holding the recent past, but nothing is being written. */
  listening: boolean;
  /** How much of the buffer is filled, in ms. Zero unless listening. */
  bufferedMs: number;
  level: number;
  elapsedMs: number;
  error?: string;
  toggle: () => Promise<void>;
  /** Set when the first-choice microphone is absent. */
  micNote?: string;
  /** Which microphone the next recording would use, in words. */
  micLabel?: string;
  /** Something true about the current setup that the recordist should know. */
  notice?: string;
  /** The earbud button is claimed and earbuds are connected to press it. */
  headsetArmed: boolean;
  /**
   * Recordings made but not yet written down, newest last.
   *
   * Held here rather than on the list screen because the video screen creates
   * them too, and the provider is the one thing above both routes.
   */
  pending: PendingCapture[];
  /** Stand a placeholder in the list until the row exists. Returns its id. */
  beginPending: (kind: PendingCapture["kind"], durationMs?: number) => string;
  /** The row landed, or the attempt failed. Either way the spinner goes. */
  settlePending: (id: string) => void;
  /** Recording a spoken note against a capture. See domain/dictationSession. */
  dictation: DictationControl;
  /** The armed hour that records on its own. See domain/idle. */
  idle: IdleControl;
}

export interface IdleControl {
  armed: boolean;
  /** Wall-clock ms when the session stands down, for the countdown. */
  deadline: number | null;
  capturesMade: number;
  /** Why the last session ended, shown until the next arm. */
  endedReason?: "expired" | "captureCap" | "sessionFailed" | "manual";
  arm: () => Promise<void>;
  disarm: () => Promise<void>;
  /**
   * The native session's live state — phase and the trigger's meter — for
   * the armed bar to poll. A pull rather than a stream on purpose: the
   * numbers change twice a second for an hour, and a bridge event per buffer
   * would be the meter flooding the app to describe silence.
   */
  read: () => IdleSessionState | null;
}

export interface DictationControl {
  phase: "idle" | "closing" | "recording" | "saving" | "reopening";
  /** Which capture is being spoken about, while one is. */
  captureUuid?: string;
  /** Held past about to be dropped, read before the buffer closes. */
  ringLossMs: number;
  /** When the current note started, for the card's own clock. */
  startedAt: number;
  error?: string;
  start: (captureUuid: string) => Promise<void>;
  stop: () => Promise<void>;
}

