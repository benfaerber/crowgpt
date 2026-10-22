import Constants from "expo-constants";

import type { AnalysisCache } from "../data/AnalysisCache";
import type { CaptureRepository } from "../data/CaptureRepository";
import type { ContextRepository } from "../data/ContextRepository";
import type { DictationRepository } from "../data/DictationRepository";
import type { FamilyRepository } from "../data/FamilyRepository";
import type { LabelRepository } from "../data/LabelRepository";
import type { LogRepository } from "../data/LogRepository";
import type { ScoutVisitRepository } from "../data/ScoutVisitRepository";
import type { SightingRepository } from "../data/SightingRepository";
import {
  HEARTBEAT_LISTENING_DEFAULT_SEC,
  HEARTBEAT_RECORDING_DEFAULT_SEC,
} from "../domain/heartbeat";
import { IDLE_DEFAULTS } from "../domain/idle";
import { DEFAULT_FUZZ_MILES } from "../domain/location";
import type { Settings } from "../domain/settings";
import type { LocationProvider } from "../recording/LocationProvider";
import type { Recorder } from "../recording/Recorder";
import type { PermissionsManager } from "../platform/Permissions";
import type { MediaSource } from "../sync/MediaSource";
import type { MergeSpec } from "../sync/MergedWav";

/**
 * What the recorder uses before anybody has arranged a list.
 *
 * This was a stored setting, `micInput`, and it was never editable from any
 * screen — the microphone picker replaced it and writes `micPriority` instead.
 * A value that can only ever be one thing is a constant pretending to be a
 * choice, and it survived because `seedFromPin` reads it when building the list
 * for the first time.
 */
export const BUILTIN_MIC = "builtin";

export const defaultSettings: Settings = {
  // Set EXPO_PUBLIC_FIELD_SERVER_URL in mobile/.env to bake in your own server —
  // the LAN address `make field` prints. Falls back to loopback, which works
  // over USB with `make reverse`. Only EXPO_PUBLIC_* vars reach the bundle, and
  // mobile/.env is gitignored, so nothing environment-specific enters the repo.
  fieldServerUrl: process.env.EXPO_PUBLIC_FIELD_SERVER_URL ?? "http://127.0.0.1:5100",
  enrollToken: process.env.EXPO_PUBLIC_FIELD_ENROLL_TOKEN ?? "dev-enroll",
  contributorName: "",
  // Whatever the phone calls itself — "Pixel 8" on a Pixel 8. A default that is
  // already right is the difference between a fleet of named handsets and one
  // where every row says "Unnamed recordist".
  deviceLabel: Constants.deviceName ?? "",
  claimCode: "",
  // Seeded on first launch from whatever microphones are attached, so an
  // existing install does not start with an empty list.
  micPriority: [],
  strictSync: true,
  mapShowTrees: false,
  mapShowScout: false,
  mapFamilyHalos: false,
  mapHiddenSpecies: [],
  mapHiddenRegions: [],
  mapShowRail: true,
  // On by default. A field recording peaks around -30 dBFS and reviewing one
  // otherwise means holding the phone against your ear at full volume; nothing
  // stored is changed, so there is no cost to being wrong about this.
  normalizePlayback: true,
  // Every capture that exists was recorded under this understanding, and
  // defaulting the other way would relabel data rather than protect anybody.
  // New recordists are asked in Settings.
  locationPrecision: "exact",
  censorCoords: true,
  fuzzMiles: DEFAULT_FUZZ_MILES,
  homeRegion: "",
  regionsBackfilled: false,
  preRoll: false,
  backgroundListening: false,
  headsetTrigger: false,
  volumeShutter: false,
  heartbeatListening: false,
  heartbeatRecording: false,
  heartbeatListeningSeconds: HEARTBEAT_LISTENING_DEFAULT_SEC,
  heartbeatRecordingSeconds: HEARTBEAT_RECORDING_DEFAULT_SEC,
  // The one default that is on. Everything else here buys a capability at a
  // cost worth choosing deliberately; this only costs a slide, and what it
  // prevents cannot be undone.
  captureLock: true,
  idleMode: false,
  idleArmMinutes: 60,
  idleHoldSeconds: IDLE_DEFAULTS.holdSeconds,
  idleMaxCaptureMinutes: 10,
  idleMaxCaptures: IDLE_DEFAULTS.maxCaptures,
  idleTriggerDb: IDLE_DEFAULTS.triggerDb,
  idleMinDb: IDLE_DEFAULTS.minDb,
  // Nothing remembered until the recordist answers once.
  lastObserverRole: "",
  lastDistanceBand: "",
};

export interface Adapters {
  repository: CaptureRepository;
  /** What sync uploads — a cropped view of the file. */
  media: MediaSource;
  /** The file as recorded, for waveforms and playback. */
  rawMedia: MediaSource;
  /** Crop spans by audio path, consulted by the cropped view at upload time. */
  crops: Map<string, { startSec?: number; endSec?: number }>;
  /** Merges by the joined capture's audio path, consulted at upload time. */
  merges: Map<string, MergeSpec>;
  recorder: Recorder;
  location: LocationProvider;
  permissions: PermissionsManager;
  families: FamilyRepository;
  labels: LabelRepository;
  context: ContextRepository;
  /** Things seen near a recording but not during it. See domain/sightings.ts. */
  sightings: SightingRepository;
  /** Scouting marks — where somebody went, and what was there. */
  scoutVisits: ScoutVisitRepository;
  /**
   * Spoken notes about a capture. The recordist talking, never bird audio —
   * nothing here may reach the analyzer or a species total.
   */
  dictations: DictationRepository;
  /**
   * The last analysis the server gave for each capture. Optional for the same
   * reason the log is: it holds nothing that cannot be fetched again.
   */
  analysisCache?: AnalysisCache;
  /**
   * Where the app's own log lands. Optional, and the one adapter that is:
   * everything else here is a feature, and this is the thing that reports on
   * them — an app that cannot open its log store must still record.
   */
  logs?: LogRepository;
}
