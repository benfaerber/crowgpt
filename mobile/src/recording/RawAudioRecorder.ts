import { PermissionsAndroid, Platform } from "react-native";

import RawAudio, {
  type AudioInput,
  type AudioInputPreference,
} from "../../modules/raw-audio";
import type { OrphanAudio } from "../domain/recoverCaptures";
import type {
  ActiveSessionInput,
  InputsChange,
  Recorder,
  RecordingOptions,
  RecordingSummary,
  IdleArmOptions,
  IdleChange,
  IdleSessionState,
} from "./Recorder";

/**
 * The real recorder, over the `raw-audio` native module.
 *
 * This is the only file in `src/` that imports that module, so if its surface
 * shifts the change lands here rather than across the screens.
 */
export class RawAudioRecorder implements Recorder {
  private attached: AudioInput[] = [];

  constructor(private readonly sampleRate = 48000) {}

  setBackground(enabled: boolean): Promise<boolean> {
    return RawAudio.setBackground(enabled);
  }

  async requestPermission(): Promise<boolean> {
    if (Platform.OS !== "android") return true;
    const result = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
    );
    return result === PermissionsAndroid.RESULTS.GRANTED;
  }

  isRecording(): boolean {
    return RawAudio.isRecording();
  }

  async start(options?: RecordingOptions): Promise<string> {
    // The resolved path is returned rather than dropped: a dictation's row is
    // written before the first byte lands, and it is keyed on this.
    return RawAudio.startRecording({
      sampleRate: options?.sampleRate ?? this.sampleRate,
      input: (options?.input as AudioInputPreference) ?? "builtin",
      prefix: options?.prefix,
    });
  }

  startListening(options: {
    input?: string;
    preRollSeconds: number;
    background?: boolean;
  }): Promise<void> {
    return RawAudio.startListening({
      sampleRate: this.sampleRate,
      input: (options.input as AudioInputPreference) ?? "builtin",
      preRollSeconds: options.preRollSeconds,
      background: options.background ?? false,
    });
  }

  stopListening(): Promise<void> {
    return RawAudio.stopListening();
  }

  swapListening(options: { input?: string; preRollSeconds: number }): Promise<void> {
    return RawAudio.swapListening({
      sampleRate: this.sampleRate,
      input: (options.input as AudioInputPreference) ?? "builtin",
      preRollSeconds: options.preRollSeconds,
    });
  }

  activeInput(): ActiveSessionInput | null {
    return RawAudio.activeInput();
  }

  isListening(): boolean {
    return Platform.OS === "android" && RawAudio.isListening();
  }

  acquireMediaButton(): Promise<void> {
    return RawAudio.acquireMediaButton();
  }

  releaseMediaButton(): Promise<void> {
    return RawAudio.releaseMediaButton();
  }

  setVolumeShutter(enabled: boolean): void {
    if (Platform.OS !== "android") return;
    RawAudio.setVolumeShutter(enabled);
  }

  onMediaButton(listener: () => void): () => void {
    const subscription = RawAudio.addMediaButtonListener(() => listener());
    return () => subscription.remove();
  }

  onSessionFailure(
    listener: (event: { message: string; whileRecording: boolean }) => void,
  ): () => void {
    const subscription = RawAudio.addSessionFailureListener(listener);
    return () => subscription.remove();
  }

  async hasBluetoothOutput(): Promise<boolean> {
    return Platform.OS === "android" && (await RawAudio.hasBluetoothOutput());
  }

  async recoverOrphans(known: string[]): Promise<OrphanAudio[]> {
    if (Platform.OS !== "android") return [];
    return RawAudio.recoverOrphans(known);
  }

  playCue(cue: "started" | "stopped" | "failed"): Promise<void> {
    return RawAudio.playCue(cue);
  }

  setHeartbeat(options: {
    listeningSeconds: number;
    recordingSeconds: number;
  }): Promise<void> {
    return RawAudio.setHeartbeat(options);
  }

  /**
   * The microphones as of the last look.
   *
   * Synchronous on purpose and deliberately not fresh: it is read while
   * rendering and at the moment Record is pressed, and the real enumeration
   * walks the audio HAL. Doing that inline froze the interface exactly when
   * somebody was trying to record. `refreshInputs` is what actually asks.
   */
  onInputsChanged(listener: (change: InputsChange) => void): () => void {
    const subscription = RawAudio.addInputsChangedListener((event) => listener(event));
    return () => subscription.remove();
  }

  listInputs(): AudioInput[] {
    return this.attached;
  }

  /** Ask the OS again, and remember the answer. */
  async refreshInputs(): Promise<AudioInput[]> {
    if (Platform.OS !== "android") return [];
    this.attached = await RawAudio.listInputs();
    return this.attached;
  }

  async stop(): Promise<RecordingSummary> {
    const result = await RawAudio.stopRecording();
    return {
      path: result.path,
      failure: result.failure ?? null,
      durationMs: result.durationMs,
      sampleRate: result.sampleRate,
      bytes: result.bytes,
      channels: 1,
      device: result.device,
      inputHonoured: result.inputHonoured,
      preRollSec: result.preRollSec,
    };
  }

  onLevel(listener: (level: number) => void): () => void {
    const subscription = RawAudio.addAudioLevelListener(({ level }) => listener(level));
    return () => subscription.remove();
  }

  setIdle(options: IdleArmOptions | null): Promise<void> {
    return RawAudio.setIdle(options);
  }

  idleState(): IdleSessionState | null {
    return RawAudio.idleState();
  }

  onIdle(listener: (change: IdleChange) => void): () => void {
    const subscription = RawAudio.addIdleListener(listener);
    return () => subscription.remove();
  }
}
