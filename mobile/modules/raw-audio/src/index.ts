import {
  NativeModule,
  requireNativeModule,
  type EventSubscription,
} from "expo-modules-core";

/**
 * Android only. There is no iOS module at all — a Swift stub lived here once,
 * never compiled against a real iPhone, and untested code that looks
 * functional is worse than no code (`git log` has it, and its header explains
 * why `unprocessed` cannot even be asserted on iOS). On iOS this import
 * throws at requireNativeModule.
 */

/**
 * Which microphone to record through.
 *
 * `"builtin"` pins the phone's own mic and is the default. Android otherwise
 * routes capture to a connected Bluetooth headset, whose SCO path is narrowband
 * and speech-processed — fine for a call, ruinous for a bird call, and invisible
 * until you listen to the recording.
 *
 * `"auto"` restores that default routing. `"type:<n>"` asks for a specific
 * attached input; see `listInputs()`.
 */
export type AudioInputPreference = "builtin" | "auto" | `type:${number}`;

export type AudioInput = {
  /** Pass this back as `input` to select it. */
  preference: AudioInputPreference;
  type: number;
  typeLabel: string;
  name: string;
  isBuiltIn: boolean;
  isExternal: boolean;
};

export type RecordingResult = {
  /** Absolute path to the recorded WAV in the app cache. */
  path: string;
  /**
   * Why the capture stopped early, or null. Set means the audio is shorter than
   * the button was held — a revoked microphone, a dead audio server, a full
   * disk. See WavRecorder's capture loop.
   */
  failure?: string | null;
  durationMs: number;
  sampleRate: number;
  bytes: number;
  /** The audio source actually used, read back from the audio policy. */
  source: string;
  /** false when the record path couldn't be read back, so `source` is the request. */
  sourceConfirmed: boolean;
  device: string | null;
  /** The preference this capture was started with. */
  requestedInput: AudioInputPreference;
  /**
   * Seconds of this recording that happened *before* the button was pressed.
   * Zero unless listening was running.
   */
  preRollSec: number;
  /**
   * Whether the audio policy accepted the pin. `null` when none was asked for
   * (`"auto"`). A `false` with `device: "BLUETOOTH_SCO"` is the failure worth
   * seeing — the recording went through earbuds after all.
   */
  inputHonoured: boolean | null;
  /** Capture effects attached to the record path, e.g. ["AEC","NS"]. Normally empty. */
  effects: string[];
  /** Measured: no capture effects were attached. null if the path wasn't readable. */
  unprocessed: boolean | null;
  /** Whether the device certifies an UNPROCESSED source (CDD 5.11). Not the same thing. */
  certifiedUnprocessed: boolean;
};

/**
 * Which microphone the open session is actually on.
 *
 * The one question the app could not previously ask. Everything else about the
 * microphone is either a stored preference or an enumeration of what is plugged
 * in — both of which describe the *next* recording. This describes the one that
 * is open, and the two disagree whenever a microphone arrives after the buffer
 * has started.
 */
export type ActiveInput = {
  /** The preference this session was opened with. */
  requested: AudioInputPreference;
  /**
   * Where the audio is really coming from, as a preference so it compares
   * directly with `requested`. Null until the policy has chosen, which is the
   * first read with data in it.
   */
  routed: AudioInputPreference | null;
  /** The same device as a label, e.g. "USB_HEADSET". Null until routed is. */
  routedLabel: string | null;
  /** Whether the policy accepted the pin. Null when none was asked for. */
  honoured: boolean | null;
  /** True while writing a capture, false while only holding pre-roll. */
  recording: boolean;
};

export type AudioLevelEvent = { level: number }; // 0..1 RMS meter

export type ProbedEffect = {
  type: string;
  name: string;
  implementor: string;
  mode: string;
};

/** What the audio policy actually did with a source request, read back live. */
export type ProbedSource = {
  label: string;
  requestedSource: number;
  opened: boolean;
  state?: string;
  audioSessionId?: number;
  configuration?: {
    clientAudioSource: number;
    clientAudioSourceLabel: string;
    audioSource: number | string;
    deviceLabel: string;
    effects?: ProbedEffect[];
    clientEffects?: ProbedEffect[];
    clientSilenced?: boolean;
  } | null;
  effectControl?: Record<string, Record<string, unknown>>;
  peakDbfs?: number;
  rmsDbfs?: number;
  path?: string;
  error?: string;
};

export type ProbeOptions = {
  sampleRate?: number;
  /** Capture window per source. Longer windows suit controlled A/B stimuli. */
  millisPerSource?: number;
  /** Write one WAV per source to the app cache for offline comparison. */
  keepAudio?: boolean;
};

export type SourceProbeReport = {
  device: string;
  androidRelease: string;
  sdkInt: number;
  /** Raw AudioManager property — null means "unknown", not "no". */
  propertyRaw: string | null;
  propertyIsNull: boolean;
  effectsAvailable: { agc: boolean; ns: boolean; aec: boolean };
  sources: ProbedSource[];
};

/**
 * Fires when a microphone is plugged in or pulled out.
 *
 * A removal carries why the disconnect cue did or did not speak. That is here
 * rather than in a native log because the phone is debugged in a park: the cue
 * shipped, stayed silent in the field, and left nobody able to say whether the
 * removal never matched the mic in use, the phrase had never been rendered on
 * this handset, or the words played into earbuds that had gone with it.
 */
export type InputsChangedEvent = {
  reason: "added" | "removed";
  /** `AudioDeviceInfo.getType()` of everything that just went. */
  removedTypes?: number[];
  /** The microphones in play: the open session's, and any that just died. */
  routedTypes?: number[];
  /** Whether one of those routes is a session that is still open. */
  routeLive?: boolean;
  /** What the cue managed, or absent when it deliberately stayed quiet. */
  said?: DisconnectCueOutcome;
  /** Where the started player was actually routed ("type:productName"). */
  cueRoute?: string;
  /** Whether the focus request that clears a fade was granted. */
  cueFocus?: boolean;
};

/**
 * What the "microphone disconnected" cue actually produced.
 *
 * `"tone"` is the one worth acting on: the cue fired and the player refused to
 * start the bundled recording, so it could only beep — indistinguishable in a
 * pocket from the failure tone a dead recording makes.
 */
export type DisconnectCueOutcome = "words" | "tone" | "buzz";

/**
 * What the cue system would do right now, without making a sound.
 *
 * `bluetoothOutput: false` is on its own enough to explain a cue nobody heard:
 * every cue is held back from the phone's own speaker, so with nothing paired
 * they are all a vibration.
 */
export type CueOutputState = {
  bluetoothOutput: boolean;
};

/**
 * Fires on a headset play/pause tap while the trigger holds the MediaSession.
 * `keyCode` is absent when the press arrived as a transport control (an
 * assistant) rather than a key.
 */
export type MediaButtonEvent = { keyCode?: number };

/**
 * Fires when the open microphone session dies on its own — a revoked mic, a
 * dead audio server, a full disk. The session is already over when this
 * arrives: with `whileRecording`, call `stopRecording` to collect what was
 * written and why it stopped; without it, the buffer is gone and listening
 * must be reopened deliberately.
 */
export type SessionFailureEvent = { message: string; whileRecording: boolean };

/** The confirmation sounds — started high, stopped low, failed unmistakably. */
export type RecorderCue = "started" | "stopped" | "failed";

/**
 * The idle trigger's numbers. Every default and bound is explained in
 * `src/domain/idle.ts`, which is the JS mirror of the native machine.
 */
export type IdleOptions = {
  armSeconds?: number;
  holdSeconds?: number;
  maxCaptureSeconds?: number;
  maxCaptures?: number;
  triggerDb?: number;
  minDb?: number;
  /** Close the microphone and the service when the session stands down. Set
   *  when arming is what opened them; a buffer somebody had open for its own
   *  sake survives the session. */
  stopListeningOnDisarm?: boolean;
  /** The deadline as words for the notification — "until 8:03 PM". */
  untilLabel?: string;
};

/**
 * Fires while idle mode is armed. `start` and `stop` are the trigger
 * asking JS to drive the normal record path — same shape as the headset
 * button, so captures are made in exactly one place. `disarmed` says the
 * session ended and why.
 */
export type IdleEvent = {
  action: "start" | "stop" | "disarmed";
  reason?: "expired" | "captureCap" | "sessionFailed" | "manual";
  capturesMade?: number;
};

/** What the armed session is doing, for the UI to re-sync from. */
export type IdleState = {
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
  /** The live meter: the crow-band level of the last half-second buffer, the
   *  measured floor it was judged against, and the line it fires over. */
  bandDb: number;
  floorDb: number;
  thresholdDb: number;
};

/**
 * Audio found on disk that no capture accounts for — a recording whose process
 * was killed before it could be closed and entered. Its header has been
 * repaired from the file's real length; `modifiedAt` is epoch millis and the
 * only evidence of when it was recorded.
 */
export type OrphanCapture = {
  path: string;
  bytes: number;
  durationMs: number;
  sampleRate: number;
  modifiedAt: number;
};

type RawAudioEvents = {
  onAudioLevel: (event: AudioLevelEvent) => void;
  onInputsChanged: (event: InputsChangedEvent) => void;
  onMediaButton: (event: MediaButtonEvent) => void;
  onSessionFailure: (event: SessionFailureEvent) => void;
  onIdle: (event: IdleEvent) => void;
};

declare class RawAudioNativeModule extends NativeModule<RawAudioEvents> {
  isUnprocessedSupported(): boolean;
  isRecording(): boolean;
  isListening(): boolean;
  activeInput(): ActiveInput | null;
  isOtherAudioPlaying(): boolean;
  startListening(options: {
    sampleRate?: number;
    input?: string;
    preRollSeconds?: number;
    background?: boolean;
  }): Promise<void>;
  stopListening(): Promise<void>;
  /** Reopen the open session on a new input, under the live service. */
  swapListening(options: {
    sampleRate?: number;
    input?: string;
    preRollSeconds?: number;
  }): Promise<void>;
  /** Start or stop holding the microphone from the background, mid-session. */
  setBackground(enabled: boolean): Promise<boolean>;
  listInputs(): Promise<AudioInput[]>;
  startRecording(options: {
    sampleRate?: number;
    input?: string;
    /** Filename prefix. Anything that is not a field capture must set it. */
    prefix?: string;
  }): Promise<string>;
  stopRecording(): Promise<RecordingResult>;
  probeAudioSources(options: ProbeOptions): Promise<SourceProbeReport>;
  acquireMediaButton(): Promise<void>;
  releaseMediaButton(): Promise<void>;
  setVolumeShutter(enabled: boolean): void;
  playCue(kind: RecorderCue): Promise<void>;
  setHeartbeat(options: {
    listeningSeconds?: number;
    recordingSeconds?: number;
  }): Promise<void>;
  hasBluetoothOutput(): Promise<boolean>;
  testDisconnectCue(throughSpeaker?: boolean): Promise<DisconnectCueOutcome>;
  cueOutputState(): Promise<CueOutputState>;
  recoverOrphans(known: string[]): Promise<OrphanCapture[]>;
  setIdle(options: IdleOptions | null): Promise<void>;
  idleState(): IdleState | null;
}

const RawAudioModule = requireNativeModule<RawAudioNativeModule>("RawAudio");

/**
 * Whether the device *certifies* an unprocessed source (Android CDD 5.11). A
 * `false` here does not mean the capture is processed — read `unprocessed` on the
 * recording result for that, which is measured per capture.
 *
 * Android only; throws on iOS, where this module is a stub.
 */
export function isUnprocessedSupported(): boolean {
  return RawAudioModule.isUnprocessedSupported();
}

export function isRecording(): boolean {
  return RawAudioModule.isRecording();
}

/** The mic is open and holding pre-roll, but nothing is being written. */
export function isListening(): boolean {
  return RawAudioModule.isListening();
}

/**
 * Which microphone the open session is on, or null when nothing is open.
 *
 * Ask this rather than re-deriving it from the preference list: the list says
 * what the next session would choose, and a session already running does not
 * revisit that choice.
 */
export function activeInput(): ActiveInput | null {
  return RawAudioModule.activeInput();
}

/**
 * Whether another app is playing audio right now.
 *
 * The variable that decides whether the headset button reaches us: Android
 * gives it to whichever app played most recently, so one that has not stopped
 * is one still winning.
 */
export function isOtherAudioPlaying(): boolean {
  return RawAudioModule.isOtherAudioPlaying();
}

/**
 * Open the microphone and keep the last few seconds in memory.
 *
 * By the time a call has been heard and the button reached, it is over — that
 * is the length of a human reaction against the length of a caw, and the button
 * always loses. Listening first means `startRecording` begins in the past.
 *
 * The microphone stays open until `stopListening`, which is real battery drain
 * and a phone that is genuinely recording. It is a mode to enter deliberately,
 * not a default.
 */
export function startListening(options?: {
  sampleRate?: number;
  input?: AudioInputPreference;
  preRollSeconds?: number;
  /**
   * Survive the screen going off, via a foreground service and a notification
   * that cannot be dismissed. Off means the microphone closes when the app
   * stops being visible, which is Android's default and costs nothing.
   */
  background?: boolean;
}): Promise<void> {
  return RawAudioModule.startListening(options ?? {});
}

export function stopListening(): Promise<void> {
  return RawAudioModule.stopListening();
}

/**
 * Reopen the rolling buffer on a different microphone without ending pocket
 * listening.
 *
 * Not the same as `stopListening` + `startListening`: stopping takes the
 * foreground service down, and a backgrounded app cannot start a new one
 * (Android 12+) — so that pair loses pocket listening on any route change
 * that happens out of a pocket, which is where route changes happen. The
 * swap recreates the session under the live service; the service is never
 * touched unless the reopen fails, in which case it is stopped so the
 * notification cannot claim a microphone nobody holds.
 *
 * Rejects with ERR_LISTEN_SWAP when nothing is listening or the reopen
 * fails — the caller must surface that, not shrug.
 */
export function swapListening(options?: {
  sampleRate?: number;
  input?: AudioInputPreference;
  preRollSeconds?: number;
}): Promise<void> {
  return RawAudioModule.swapListening(options ?? {});
}

/**
 * Hold the microphone from the background, or stop doing so, mid-session.
 *
 * Separate from `startListening` because the answer can change while the mic is
 * open: switching pocket listening off used to leave the foreground service —
 * and its notification, and the background microphone — running until something
 * else happened to stop them.
 */
export function setBackground(enabled: boolean): Promise<boolean> {
  return RawAudioModule.setBackground(enabled);
}

/** Every microphone currently attached, built-in first. */
export function listInputs(): Promise<AudioInput[]> {
  return RawAudioModule.listInputs();
}

/**
 * Start capturing 48 kHz mono 16-bit WAV. Requires RECORD_AUDIO. Resolves the
 * file path.
 *
 * Defaults to the built-in mic rather than whatever Android would route to,
 * because the routed choice is usually a paired headset and that silently ruins
 * the recording.
 */
export function startRecording(options?: {
  sampleRate?: number;
  input?: AudioInputPreference;
  /**
   * Filename prefix. Leave it alone for a field capture.
   *
   * Anything recorded through here that is NOT bird audio must set it, or the
   * orphan sweep will claim the file as an abandoned capture at the next launch
   * and enter it into the corpus. See OrphanCaptures.CAPTURE_PREFIX.
   */
  prefix?: string;
}): Promise<string> {
  return RawAudioModule.startRecording(options ?? {});
}

export function stopRecording(): Promise<RecordingResult> {
  return RawAudioModule.stopRecording();
}

/**
 * Android only. Opens each candidate mic source in turn and reports what the OS
 * really provided — selected source, attached effects, level. Writes one WAV per
 * source to the app cache and mirrors the report to logcat (tag `RawAudioProbe`).
 * Diagnostic: does not touch the capture path.
 */
export function probeAudioSources(
  options?: ProbeOptions,
): Promise<SourceProbeReport> {
  return RawAudioModule.probeAudioSources(options ?? {});
}

/** Native modules are themselves EventEmitters as of SDK 52 — no wrapper needed. */
export function addAudioLevelListener(
  listener: (event: AudioLevelEvent) => void,
): EventSubscription {
  return RawAudioModule.addListener("onAudioLevel", listener);
}

/**
 * Watch for microphones appearing and disappearing.
 *
 * `listInputs` is a cache, so something has to say when it is stale. Nothing
 * did, and a mic plugged in while the record screen was open stayed invisible.
 */
export function addInputsChangedListener(
  listener: (event: InputsChangedEvent) => void,
): EventSubscription {
  return RawAudioModule.addListener("onInputsChanged", listener);
}

/**
 * Take the headset play/pause button — and with it, take it away from every
 * other app until `releaseMediaButton`. Idempotent, so the setting can assert
 * it without counting.
 */
export function acquireMediaButton(): Promise<void> {
  return RawAudioModule.acquireMediaButton();
}

export function releaseMediaButton(): Promise<void> {
  return RawAudioModule.releaseMediaButton();
}

/**
 * Claim the volume keys as a shutter, for Bluetooth camera remotes — HID
 * keyboards hardwired to send volume-up. Presses arrive as onMediaButton,
 * the same event as the headset button, so there is one trigger path.
 *
 * Narrower than the headset button on purpose: the keys come through the
 * Activity, so this only fires with the app in front and the screen on —
 * and while claimed, no key (remote or the phone's own rocker) changes the
 * volume inside the app. Synchronous because it only flips a flag.
 */
export function setVolumeShutter(enabled: boolean): void {
  RawAudioModule.setVolumeShutter(enabled);
}

/**
 * A tone in the connected earbuds, or a vibration when none are — the only
 * feedback channel a phone in a bag has.
 */
export function playCue(kind: RecorderCue): Promise<void> {
  return RawAudioModule.playCue(kind);
}

/**
 * Play "microphone disconnected" now, and report what came out of the phone.
 *
 * The real trigger needs the Rode, an open session, and the nerve to pull a
 * microphone off mid-recording, which is why this cue could ship broken and
 * stay that way: nothing could ask the phone whether it was *able* to speak.
 */
export function testDisconnectCue(
  /**
   * Lift the rule that keeps the words off the phone's own speaker. False in
   * the field, where a phrase out loud lands in the recording; true on a desk,
   * where that rule is the whole reason the test appears to do nothing.
   */
  throughSpeaker = false,
): Promise<DisconnectCueOutcome> {
  return RawAudioModule.testDisconnectCue(throughSpeaker);
}

/** What the cue system would do right now, without making a sound. */
export function cueOutputState(): Promise<CueOutputState> {
  return RawAudioModule.cueOutputState();
}

/**
 * Find recordings a killed process left behind, and repair their headers.
 *
 * `known` must be every audio path the database holds, so healthy captures and
 * a live recording are excluded. Returns what was recovered; entering it in the
 * database is the caller's job.
 */
export function recoverOrphans(known: string[]): Promise<OrphanCapture[]> {
  return RawAudioModule.recoverOrphans(known);
}

/**
 * Say the recorder's state into the ears on two independent cadences — a tick
 * while listening, a double beep while recording, silence while idle. Zero
 * (or omitted) for a state means that heartbeat is off; a switched-off state
 * stays silent rather than borrowing the other's sound. Scheduled natively:
 * JS timers pause with the activity, and the state matters most from a
 * pocket. Each tone briefly ducks whatever else is playing.
 */
export function setHeartbeat(options: {
  listeningSeconds?: number;
  recordingSeconds?: number;
}): Promise<void> {
  return RawAudioModule.setHeartbeat(options);
}

/** Whether any Bluetooth output is connected — earbuds to press, ears to cue. */
export function hasBluetoothOutput(): Promise<boolean> {
  return RawAudioModule.hasBluetoothOutput();
}

/** Fires on each tap of the headset button while `acquireMediaButton` holds it. */
export function addMediaButtonListener(
  listener: (event: MediaButtonEvent) => void,
): EventSubscription {
  return RawAudioModule.addListener("onMediaButton", listener);
}

/**
 * Fires when the microphone session dies on its own — see SessionFailureEvent.
 * The one push in this module that exists for when nobody is looking at the
 * screen: a buffer dying silently in a pocket used to be discovered at the
 * next stop, hours later.
 */
export function addSessionFailureListener(
  listener: (event: SessionFailureEvent) => void,
): EventSubscription {
  return RawAudioModule.addListener("onSessionFailure", listener);
}

/**
 * Arm the idle trigger over the open listening session, or disarm with
 * null. Rejects when nothing is listening: a trigger with no PCM to read
 * would be armed in name only, which is the silent failure worse than the
 * refusal. Disarming ends any auto capture in flight and files it as usual.
 */
export function setIdle(options: IdleOptions | null): Promise<void> {
  return RawAudioModule.setIdle(options);
}

/** The armed session's state, or null when nothing is armed. Synchronous —
 *  it reads fields the trigger has already published, like `activeInput`. */
export function idleState(): IdleState | null {
  return RawAudioModule.idleState();
}

/** Fires with the trigger's requests while idle mode is armed. */
export function addIdleListener(
  listener: (event: IdleEvent) => void,
): EventSubscription {
  return RawAudioModule.addListener("onIdle", listener);
}

export default {
  addInputsChangedListener,
  addMediaButtonListener,
  addSessionFailureListener,
  acquireMediaButton,
  releaseMediaButton,
  setVolumeShutter,
  playCue,
  setHeartbeat,
  hasBluetoothOutput,
  testDisconnectCue,
  cueOutputState,
  recoverOrphans,
  isUnprocessedSupported,
  isRecording,
  isListening,
  activeInput,
  isOtherAudioPlaying,
  startListening,
  stopListening,
  swapListening,
  setBackground,
  listInputs,
  startRecording,
  stopRecording,
  probeAudioSources,
  addAudioLevelListener,
  setIdle,
  idleState,
  addIdleListener,
};
