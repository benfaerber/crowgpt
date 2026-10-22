/**
 * The recording seam.
 *
 * The UI talks to this, not to `modules/raw-audio` directly. That module is the
 * one piece of the app with genuinely platform-specific behavior and it changes
 * independently of the screens; keeping an interface in between means the app
 * compiles and can be reasoned about without it, and a fake recorder can drive
 * the UI with no microphone.
 */

import type { OrphanAudio } from "../domain/recoverCaptures";

export interface RecordingSummary {
  /** Absolute path to the WAV written on the device. */
  path: string;
  /** Set when the capture stopped before the user did. Null on a healthy one. */
  failure?: string | null;
  durationMs: number;
  sampleRate: number;
  channels: number;
  bytes: number;
  /** Which microphone the OS actually routed to, e.g. "BUILTIN_MIC". */
  device?: string | null;
  /** False when a pinned input was refused — the capture used something else. */
  inputHonoured?: boolean | null;
  /** Seconds captured before the button was pressed, via the rolling buffer. */
  preRollSec?: number;
}

export interface RecordingOptions {
  sampleRate?: number;
  /** "builtin" (default), "auto", or "type:<n>" — see modules/raw-audio. */
  input?: string;
  /**
   * Filename prefix. Leave unset for a field capture.
   *
   * A spoken note must set it: the orphan sweep recognises an abandoned capture
   * by its name, so a memo left behind by a killed process would otherwise be
   * entered into the corpus as bird audio.
   */
  prefix?: string;
}

/** One attached microphone, as the picker needs to describe it. */
export interface AudioInputDescription {
  preference: string;
  type: number;
  typeLabel: string;
  name: string;
  isBuiltIn: boolean;
  isExternal: boolean;
}

/**
 * What the open microphone session is actually doing, as opposed to what the
 * settings say the next one should do.
 *
 * Declared here rather than imported from the native module so that the rest of
 * `src/` keeps depending only on this interface — RawAudioRecorder is the one
 * file allowed to know the module's shape.
 */
export interface ActiveSessionInput {
  /** The preference this session was opened with. */
  requested: string;
  /**
   * Where the audio is really coming from, as a preference so it compares with
   * `requested` directly. Null until the audio policy has chosen a route, which
   * is a moment after the session opens.
   */
  routed: string | null;
  routedLabel: string | null;
  /** Whether the policy accepted the pin. Null when nothing was pinned. */
  honoured: boolean | null;
  /** Writing a capture, as opposed to only holding pre-roll. */
  recording: boolean;
}

/**
 * A microphone appearing or disappearing, and — on a removal — what the
 * disconnect cue made of it.
 *
 * The diagnosis travels with the event because this is decided natively, inside
 * an audio device callback, and the only way anybody finds out what a phone in a
 * park did is the app log.
 */
export interface InputsChange {
  reason: "added" | "removed";
  removedTypes?: number[];
  /** The microphones in play: the open session's, and any that just died. */
  routedTypes?: number[];
  routeLive?: boolean;
  /** What the cue said, or absent when it deliberately stayed quiet. */
  said?: DisconnectCueOutcome;
  /** Where the started player was actually routed ("type:productName"). */
  cueRoute?: string;
  /** Whether the focus request that clears a fade was granted. */
  cueFocus?: boolean;
}

/**
 * What the disconnect cue produced. `"tone"` means the player refused to
 * start the bundled recording, so the cue could only beep.
 */
export type DisconnectCueOutcome = "words" | "tone" | "buzz";

/**
 * The idle trigger's numbers, as the armed session receives them. Every
 * default and bound is reasoned about in domain/idle.ts.
 */
export interface IdleArmOptions {
  armSeconds: number;
  holdSeconds: number;
  maxCaptureSeconds: number;
  maxCaptures: number;
  triggerDb: number;
  minDb: number;
  /** Close the microphone and service when the session stands down — set when
   *  arming is what opened them. */
  stopListeningOnDisarm: boolean;
  /** The deadline as words for the notification — "until 8:03 PM". */
  untilLabel: string;
}

/**
 * The trigger asking for something while idle mode is armed. `start` and
 * `stop` drive the normal record path, exactly as a headset press does;
 * `disarmed` says the session ended and why.
 */
export interface IdleChange {
  action: "start" | "stop" | "disarmed";
  reason?: "expired" | "captureCap" | "sessionFailed" | "manual";
  capturesMade?: number;
}

/** What the armed session is doing, for the UI to re-sync from. */
export interface IdleSessionState {
  phase:
    | "armed"
    | "triggered"
    | "recording"
    | "stopping"
    | "cooldown"
    | "suspended"
    | "disarmed";
  remainingMs: number;
  capturesMade: number;
  /** The live meter: last buffer's crow-band level, the measured floor it
   *  was judged against, and the line it fires over — all dBFS. */
  bandDb: number;
  floorDb: number;
  thresholdDb: number;
}

export interface Recorder {
  /** Ask for microphone access. Resolves false if the user declined. */
  requestPermission(): Promise<boolean>;
  /**
   * Start or stop holding the microphone from the background while a listening
   * session is live. Absent on implementations that cannot.
   */
  setBackground?(enabled: boolean): Promise<boolean>;
  isRecording(): boolean;
  /** Resolves the path being written, which a dictation row is keyed on. */
  start(options?: RecordingOptions): Promise<string | void>;
  /**
   * Microphones attached right now, for the picker. Optional because a fake
   * recorder driving the UI has no hardware to enumerate.
   */
  /** The last enumeration, without asking the OS again. */
  listInputs?(): AudioInputDescription[];
  /** Ask the OS which microphones are attached, and remember it. */
  refreshInputs?(): Promise<AudioInputDescription[]>;
  /**
   * Call back when a microphone is plugged in or pulled out; returns an
   * unsubscribe.
   *
   * Needed because `listInputs` is a cache. Without a push, the app cannot tell
   * that the mic the recordist just connected is now there, and goes on saying
   * it is not.
   */
  onInputsChanged?(listener: (change: InputsChange) => void): () => void;
  /**
   * Hold the last `preRollSeconds` in memory so the next recording can begin
   * before the button was pressed. Optional: a fake recorder has no microphone.
   */
  startListening?(options: {
    input?: string;
    preRollSeconds: number;
    /** Keep the microphone through screen-off, at the cost of a notification. */
    background?: boolean;
  }): Promise<void>;
  stopListening?(): Promise<void>;
  /**
   * Reopen the rolling buffer on a different microphone without ending
   * pocket listening. A stop/start pair looks the same and is not: stopping
   * takes the foreground service down, and a backgrounded app cannot start
   * a new one — the swap happens under the live service or not at all.
   * Rejects when nothing is listening or the reopen fails.
   */
  swapListening?(options: {
    input?: string;
    preRollSeconds: number;
  }): Promise<void>;
  isListening?(): boolean;
  /**
   * Which microphone the open session is actually on, or null when none is.
   *
   * The only honest answer to "which mic are we on". `listInputs` and the
   * preference list together describe what the *next* session would pick, and a
   * session already open never revisits that — so anything shown to the
   * recordist about the current recording has to come from here.
   */
  activeInput?(): ActiveSessionInput | null;
  /**
   * Claim the headset play/pause button, or give it back. Claiming is
   * zero-sum — while held, no other app's tap does anything — which is why
   * these are explicit calls the setting drives rather than a side effect of
   * anything else.
   */
  acquireMediaButton?(): Promise<void>;
  releaseMediaButton?(): Promise<void>;
  /**
   * Claim or release the volume keys as a shutter, for Bluetooth camera
   * remotes. Presses arrive on `onMediaButton` like the headset button's, but
   * by a narrower path: the Activity's key events, so app in front and screen
   * on. While claimed, volume keys toggle recording instead of the volume.
   */
  setVolumeShutter?(enabled: boolean): void;
  /** Call back on each tap of the claimed button; returns an unsubscribe. */
  onMediaButton?(listener: () => void): () => void;
  /**
   * Call back when the open microphone session dies on its own — a revoked
   * mic, a dead audio server, a full disk. The session is already over when
   * the listener runs: with `whileRecording`, `stop()` still collects what was
   * written and why; without it, the buffer is gone and listening must be
   * reopened deliberately. Returns an unsubscribe.
   */
  onSessionFailure?(
    listener: (event: { message: string; whileRecording: boolean }) => void,
  ): () => void;
  /**
   * Say the recorder's state into the ears on two independent cadences — a
   * tick for listening, a double beep for recording, silence when idle. Zero
   * for a state means that heartbeat is off; the interval carries the switch.
   * Runs natively so it keeps ticking from a pocket, where JS timers pause
   * with the screen.
   */
  setHeartbeat?(options: {
    listeningSeconds: number;
    recordingSeconds: number;
  }): Promise<void>;
  /** Whether a Bluetooth output is connected — the armed indicator's other half. */
  hasBluetoothOutput?(): Promise<boolean>;
  /**
   * Audio on disk that no capture accounts for, with its header repaired.
   * `known` is every path the database holds, so healthy and live captures are
   * excluded by the caller. See domain/recoverCaptures.ts.
   */
  recoverOrphans?(known: string[]): Promise<OrphanAudio[]>;
  /**
   * Confirm into the ears what just happened. The recordist's phone is in a
   * bag: this is the only channel that says a button press worked, and
   * "failed" exists because a press that silently did nothing is
   * indistinguishable from a recording until the walk is over.
   */
  playCue?(cue: "started" | "stopped" | "failed"): Promise<void>;
  stop(): Promise<RecordingSummary>;
  /** Subscribe to the 0..1 RMS meter. Returns an unsubscribe function. */
  onLevel(listener: (level: number) => void): () => void;
  /**
   * Arm the idle trigger over the open listening session, or disarm with
   * null. Rejects when nothing is listening — a trigger with no PCM to read
   * would be armed in name only. Optional: a fake recorder has no trigger.
   */
  setIdle?(options: IdleArmOptions | null): Promise<void>;
  /** The armed session's state, or null when nothing is armed. */
  idleState?(): IdleSessionState | null;
  /** Call back with the trigger's requests; returns an unsubscribe. */
  onIdle?(listener: (change: IdleChange) => void): () => void;
}

/**
 * How much of the past the rolling buffer keeps.
 *
 * Long enough to cover hearing a call, deciding it was worth keeping, and
 * finding the button — which is several seconds more than it feels like. At
 * 48 kHz mono 16-bit this is ~1.4 MB of resident memory, which is why it isn't
 * simply set to a minute.
 */
export const PRE_ROLL_SEC = 15;
