import { AppState } from "react-native";

import type { CaptureRepository } from "../data/CaptureRepository";
import { SqliteCaptureRepository } from "../data/SqliteCaptureRepository";
import { SqliteSettingsStore, type SettingsStore } from "../data/SettingsStore";
import type { FamilyRepository } from "../data/FamilyRepository";
import type { ContextRepository } from "../data/ContextRepository";
import { SqliteContextRepository } from "../data/SqliteContextRepository";
import type { SightingRepository } from "../data/SightingRepository";
import type { DictationRepository } from "../data/DictationRepository";
import type { DictationRecord, NewDictation } from "../domain/dictations";
import { SqliteDictationRepository } from "../data/SqliteDictationRepository";
import { SqliteSightingRepository } from "../data/SqliteSightingRepository";
import type { LabelRepository } from "../data/LabelRepository";
import type { AnalysisCache } from "../data/AnalysisCache";
import { SqliteAnalysisCache } from "../data/SqliteAnalysisCache";
import type { LogRepository } from "../data/LogRepository";
import { SqliteLogRepository } from "../data/SqliteLogRepository";
import { SqliteLabelRepository } from "../data/SqliteLabelRepository";
import { currentBuild } from "./buildInfo";
import { resolveSettings, type Settings } from "../domain/settings";
import {
  rememberMics,
  resolveMic,
  seedFromPin,
  type KnownMic,
} from "../domain/micPriority";
import { captureFromOrphan, worthRecovering } from "../domain/recoverCaptures";
import { newClientUuid } from "../domain/ids";
import { deleteCaptureFiles } from "../platform/deleteCaptureFiles";
import { compatibility, type Compatibility } from "../domain/compatibility";
import { FALLBACK_CONFIG, type FleetConfig } from "../domain/config";
import { scoutLayerFromServer, scoutSpotsFromServer, type ScoutLayer, type ScoutTarget } from "../domain/scout";
import { SqliteScoutVisitRepository } from "../data/SqliteScoutVisitRepository";
import { ScoutVisitSync } from "../sync/ScoutVisitSync";
import type { ScoutVisit, VisitKind, VisitOutcome } from "../domain/scoutVisits";
import { treeLayerFromGeojson, type TreeLayer } from "../domain/trees";
import type { Identity } from "../domain/identity";
import type { ContextRecord } from "../domain/context";
import type { LabelRecord } from "../domain/labels";
import { SqliteFamilyRepository } from "../data/SqliteFamilyRepository";
import { runMigrations } from "../data/runMigrations";
import { FieldServerClient } from "../net/FieldServerClient";
import { XhrHttpClient } from "../net/XhrHttpClient";
import { DevicePermissions, type PermissionsManager } from "../platform/Permissions";
import { DeviceLocationProvider, type Fix, type LocationProvider } from "../recording/LocationProvider";
import { DeviceRegionLookup } from "../recording/RegionLookup";
import { RawAudioRecorder } from "../recording/RawAudioRecorder";
import type { Recorder } from "../recording/Recorder";
import { CroppedWavSource } from "../sync/CroppedWav";
import { MergedWavSource, type MergeSpec } from "../sync/MergedWav";
import {
  loadMergeSpecs,
  repairUnmaterialisedMerges,
  unmergeCapture,
} from "../domain/mergeCaptures";
import { deleteMergedAudio, writeMergedAudio } from "../platform/writeMergedAudio";
import { FileMediaSource } from "../sync/FileMediaSource";
import type { MediaSource } from "../sync/MediaSource";
import { SyncEngine } from "../sync/SyncEngine";
import { LogSync, type LogSyncOutcome } from "../sync/LogSync";
import { log } from "./Log";
import { reportNativeCrashes } from "./nativeCrashes";
import { deviceRandomBytes } from "../platform/random";
import { FileDownloader } from "../sync/FileDownloader";
import { Restore, type RestoreOutcome } from "../sync/Restore";
import { NormalizedWav } from "../playback/NormalizedWav";
import { PrefetchAnalysis, type PrefetchOutcome } from "../sync/PrefetchAnalysis";
import { BackfillRegions } from "../sync/BackfillRegions";
import { Annotations } from "./Annotations";
import { BUILTIN_MIC, defaultSettings, type Adapters } from "./adapters";
import { IdentityManager } from "./Identity";

export type { Settings };

/**
 * Composition root — the one place that decides which implementations the app
 * runs on, so every screen below it depends on interfaces rather than on
 * SQLite, the filesystem, or the audio module.
 */
export class AppServices {
  private client: FieldServerClient;
  private engine: SyncEngine;
  private currentSettings: Settings;
  private currentConfig: FleetConfig;
  private currentTrees: TreeLayer | null;
  private currentScout: ScoutLayer | null;
  /** Ground-truth writes — labels, context, spoken notes. See Annotations.ts. */
  private readonly annotations: Annotations;
  /** Who this phone is to the fleet. See Identity.ts. */
  private readonly ids: IdentityManager;

  constructor(
    readonly adapters: Adapters,
    settings: Settings = defaultSettings,
    private readonly store?: SettingsStore<Settings>,
    deviceToken?: string,
    identity?: Identity,
    config?: FleetConfig,
    trees?: TreeLayer,
    scout?: ScoutLayer,
  ) {
    this.currentSettings = settings;
    this.currentConfig = config ?? FALLBACK_CONFIG;
    this.currentTrees = trees ?? null;
    this.currentScout = scout ?? null;
    ({ client: this.client, engine: this.engine } = this.connection(
      settings.fieldServerUrl,
      deviceToken,
    ));
    // Both take the client as a function: `connection` rebuilds it when the
    // app points at a different server, and a collaborator holding the old one
    // would keep talking to a machine we have left.
    this.annotations = new Annotations({
      repository: adapters.repository,
      labels: adapters.labels,
      context: adapters.context,
      dictations: adapters.dictations,
      client: () => this.client,
      configVersion: () => this.currentConfig.version,
    });
    this.ids = new IdentityManager({ client: () => this.client, store }, identity);
    // The MediaSession died with the last process, but the setting survived it
    // — so the claim is re-asserted here, at the root, rather than waiting for
    // any particular screen to mount.
    if (settings.headsetTrigger) this.claimHeadsetButton(true);
    // The native flag died with the process too; the setting survived it.
    if (settings.volumeShutter) this.applyVolumeShutter(true);
    // Same shape, same reason: the native timer died with the process.
    if (settings.heartbeatListening || settings.heartbeatRecording) {
      this.applyHeartbeat(settings);
    }
  }

  /**
   * Delete captures and the audio they own.
   *
   * One place for it because deleting is three steps that must happen in order,
   * and the screens were doing only the middle one: the files go first (a row
   * without its audio is a player that spins forever), then the row, and a
   * merged capture takes its hidden parts with it — those are only reachable
   * through the capture being deleted, so leaving them would strand audio in the
   * database that no screen can ever show.
   *
   * Returns how many captures were removed, so a caller can say so.
   */
  async deleteCaptures(uuids: string[]): Promise<number> {
    let removed = 0;
    for (const uuid of uuids) {
      const capture = await this.adapters.repository.get(uuid);
      if (!capture) continue;
      // This capture's own media only. Deleting a merged capture must not take
      // its parts' audio: `remove` un-hides them on purpose, which is what
      // makes a merge undoable, and they are about to become real rows again.
      // Spoken notes go with it. A row without its audio is a player that
      // spins forever; audio without its row is disk leaked quietly, which is
      // what deleteCaptureFiles was written to stop.
      const notes = await this.adapters.dictations.forCapture(uuid);
      await deleteCaptureFiles(
        [capture.audioPath, capture.videoPath, ...notes.map((n) => n.audioPath)],
        (path, failure) => log.warn("capture", `could not delete ${path}`, failure),
      );
      for (const note of notes) await this.adapters.dictations.remove(note.uuid);
      await this.adapters.repository.remove(uuid);
      this.adapters.crops.delete(capture.audioPath);
      this.adapters.merges.delete(capture.audioPath);
      removed += 1;
    }
    if (removed > 0) log.info("capture", `deleted ${removed} capture(s)`);
    return removed;
  }

  /**
   * Bring a merge apart again — the promise the merge feature makes.
   *
   * The domain half clears the pointers and drops the row; this half cleans
   * up what the row owned: the assembled WAV under merged/ and the crop and
   * merge specs keyed by its path. The parts are never touched — they are the
   * recordings, and their being intact is what makes this only a matter of
   * forgetting. Going through `repository.remove` alone would leave the
   * assembled file on disk forever, which is the same leak deleteCaptures
   * exists to close.
   *
   * Returns how many recordings came back to the list.
   */
  async unmerge(uuid: string): Promise<number> {
    const merged = await this.adapters.repository.get(uuid);
    if (!merged) return 0;
    const restored = await unmergeCapture(this.adapters.repository, uuid);
    deleteMergedAudio(uuid);
    this.adapters.crops.delete(merged.audioPath);
    this.adapters.merges.delete(merged.audioPath);
    log.info("capture", `un-merged ${uuid} into ${restored.length} recording(s)`);
    return restored.length;
  }

  /**
   * Enter any recording a killed process left on disk.
   *
   * Measured on the Pixel 8: force-stopping the app mid-recording lost the
   * capture outright — the samples were on disk, the WAV header still said zero
   * and no row pointed at it. That is the one loss this app cannot undo,
   * happening silently, so the audio is claimed back at launch rather than left
   * for a cache sweep to delete.
   *
   * Never throws: a phone that cannot recover must still record.
   */
  async recoverAbandonedCaptures(): Promise<number> {
    const recorder = this.adapters.recorder;
    if (!recorder.recoverOrphans) return 0;
    try {
      // Every audio path the phone knows about, dictations included. Without
      // theirs, a memo the process died during is swept up and entered as a
      // FIELD CAPTURE at the next launch — Ben's voice in the corpus as bird
      // audio, which is the contamination ★ Keep exists to hold back. The
      // native `dictation_` prefix is the structural half of this guard; the
      // row written before the first byte is what makes this half work.
      const known = [
        ...await this.adapters.repository.audioPaths(),
        ...await this.adapters.dictations.audioPaths(),
      ];
      const found = worthRecovering(await recorder.recoverOrphans(known));
      for (const orphan of found) {
        const capture = captureFromOrphan(orphan, {
          uuid: newClientUuid(deviceRandomBytes),
          mediaUuid: newClientUuid(deviceRandomBytes),
        });
        await this.adapters.repository.add(capture);
        log.warn("recorder", "recovered a capture the app died during", {
          uuid: capture.uuid,
          durationMs: capture.durationMs,
          bytes: capture.bytes,
        });
      }
      return found.length;
    } catch (failure) {
      log.error("recorder", "could not sweep for abandoned recordings", failure);
      return 0;
    }
  }

  /**
   * Hold or release the headset play/pause button to match the setting.
   *
   * Owned here and not by a screen: the button must survive navigating away
   * from the capture list, and releasing must happen the moment the switch
   * goes off — "off" means YouTube has the button back, not "off once the
   * right component unmounts".
   */
  private claimHeadsetButton(enabled: boolean): void {
    const recorder = this.adapters.recorder;
    void (enabled
      ? recorder.acquireMediaButton?.()
      : recorder.releaseMediaButton?.()
    )?.catch((failure) =>
      // A trigger that silently is not armed is the failure mode this feature
      // must not have: the next button press in the field does nothing.
      log.error("recorder", enabled
        ? "could not claim the headset button"
        : "could not release the headset button", failure),
    );
    if (enabled) this.watchForegroundForButton();
    else this.stopWatchingForeground?.();
  }

  /**
   * Mirror the volume-shutter setting into the native flag. No contest to
   * re-enter and nothing taken from other apps — the keys only reach a
   * foregrounded Activity — so unlike the headset button this is one flag,
   * asserted at startup and on change.
   */
  private applyVolumeShutter(enabled: boolean): void {
    try {
      this.adapters.recorder.setVolumeShutter?.(enabled);
    } catch (failure) {
      // Same stakes as the headset button: a shutter that silently is not
      // armed reads as a remote that does nothing, in the field.
      log.error("recorder", enabled
        ? "could not claim the volume shutter"
        : "could not release the volume shutter", failure);
    }
  }

  /**
   * Start or stop the native heartbeat timer to match the settings.
   *
   * Owned here for the reason the button is: the tick must outlive whichever
   * screen is showing, and the native side already goes quiet on its own when
   * nothing is listening — so this only speaks when the *setting* changes.
   */
  private applyHeartbeat(settings: Settings): void {
    void this.adapters.recorder
      .setHeartbeat?.({
        // The interval carries the switch: zero is how "off" crosses the
        // bridge, so there is no flag for the native side to disagree with.
        listeningSeconds: settings.heartbeatListening
          ? settings.heartbeatListeningSeconds
          : 0,
        recordingSeconds: settings.heartbeatRecording
          ? settings.heartbeatRecordingSeconds
          : 0,
      })
      .catch((failure) =>
        // A heartbeat that silently is not running reads as "not recording",
        // which is worse than no heartbeat at all.
        log.error("recorder", "could not set the heartbeat cue", failure),
      );
  }

  private stopWatchingForeground?: () => void;

  /**
   * Take the button again on every trip in or out of the app.
   *
   * Claiming once, at startup, assumes nothing can take it away — and the whole
   * mechanism is a recency contest that other apps enter constantly by simply
   * playing audio. Leaving the app is when that is most likely to have happened
   * and least likely to have been noticed: whatever was opened instead almost
   * certainly made a sound.
   *
   * Both directions on purpose. Going *out* is the last moment the process is
   * reliably alive to assert itself before a walk; coming back in is the first
   * chance to repair whatever happened while it was away. Neither alone covers
   * a phone that spends the walk with the screen off.
   *
   * `acquireMediaButton` is idempotent, so re-asserting costs a silent blip and
   * a state refresh rather than a new session.
   */
  private watchForegroundForButton(): void {
    if (this.stopWatchingForeground) return;
    const subscription = AppState.addEventListener("change", () => {
      if (!this.currentSettings.headsetTrigger) return;
      void this.adapters.recorder.acquireMediaButton?.().catch((failure) =>
        log.warn("recorder", "could not re-take the headset button", failure),
      );
    });
    this.stopWatchingForeground = () => {
      subscription.remove();
      this.stopWatchingForeground = undefined;
    };
  }

  /** Build the real thing. Async because opening the local database is. */
  static async create(fallback: Settings = defaultSettings): Promise<AppServices> {
    const store = await SqliteSettingsStore.open<Settings>();
    const persisted = await store.load();
    const repository = await SqliteCaptureRepository.open();

    // Crops are applied on the way out. The sync engine asks the media source
    // for size and bytes, so presenting a cropped view here means the upload
    // path needs no idea that cropping exists.
    const crops = new Map<string, { startSec?: number; endSec?: number }>();
    // Rehydrated from the database, not remembered from when the merge was
    // made: a merged capture's audio is assembled from these, so an app
    // restarted between merging and syncing would otherwise have nothing to
    // upload and no way to say so.
    const merges = await loadMergeSpecs(repository);
    // Merges made before they were written to disk have no file behind them.
    // Repaired here rather than left broken: the audio was always derivable
    // from the parts, and the phone is the only place that knows it is wrong.
    const repaired = await repairUnmaterialisedMerges(
      repository, writeMergedAudio,
      (uuid, failure) => log.error("merge", `could not rebuild ${uuid}`, failure));
    if (repaired > 0) log.info("merge", `rebuilt ${repaired} merged capture(s)`);
    const files = new FileMediaSource();
    // Merge wraps crop, not the other way round. Each part is read through the
    // cropped view, so a capture trimmed before it was merged stays trimmed
    // inside the join — and the merged file is built from what the recordist
    // actually chose to keep. Cropping the *joined* audio instead would need
    // offsets nobody has, since the parts have already moved.
    const cropped = new CroppedWavSource(files, (path) => crops.get(path));
    const media = new MergedWavSource(cropped, (path) => merges.get(path));

    const families = await SqliteFamilyRepository.open();
    const labels = await SqliteLabelRepository.open();
    const context = await SqliteContextRepository.open();
    const sightings = await SqliteSightingRepository.open();
    const scoutVisits = await SqliteScoutVisitRepository.open();
    const dictations = await SqliteDictationRepository.open();

    const analysisCache = await SqliteAnalysisCache.open().catch((failure) => {
      log.error("db", "analysis cache would not open", failure);
      return undefined;
    });

    // Opened in its own try, and early: from here on, a failure anywhere in
    // startup is written down somewhere a phone in a park can be asked about.
    // Failing to open it must not take the app down — a missing log is worth
    // strictly less than the app it was going to describe.
    let logs: LogRepository | undefined;
    try {
      logs = await SqliteLogRepository.open();
      log.attach(logs, deviceRandomBytes);
    } catch (failure) {
      log.error("db", "log store would not open", failure);
    }
    // Only once there is somewhere to put them. What the last process died of
    // is the one class of failure JavaScript can never witness for itself.
    void reportNativeCrashes();

    // After every store has created its tables, so a step that rebuilds one
    // finds it there. Some shapes — a NOT NULL that should never have been —
    // cannot be reached by the open-time "add the column if it's missing"
    // checks, because the column is already present and merely wrong.
    const ran = await runMigrations();
    if (ran.length > 0) {
      console.log(`[schema] applied: ${ran.join(", ")}`);
      log.info("db", `migrations applied: ${ran.join(", ")}`);
    }

    return new AppServices(
      {
        repository,
        media,
        rawMedia: files,
        crops,
        merges,
        recorder: new RawAudioRecorder(),
        location: new DeviceLocationProvider(),
        permissions: new DevicePermissions(),
        families,
        labels,
        context,
        sightings,
        scoutVisits,
        dictations,
        analysisCache,
        logs,
      },
      resolveSettings(fallback, persisted.settings),
      store,
      persisted.deviceToken,
      persisted.identity,
      persisted.config,
      persisted.trees,
      persisted.scout,
    );
  }

  get repository(): CaptureRepository {
    return this.adapters.repository;
  }

  get recorder(): Recorder {
    return this.adapters.recorder;
  }

  get rawMedia(): MediaSource {
    return this.adapters.rawMedia;
  }

  /** Tell the upload path which recordings a merged capture is made of. */
  setMerge(audioPath: string, spec: MergeSpec | undefined): void {
    if (spec && spec.parts.length > 0) {
      this.adapters.merges.set(audioPath, spec);
    } else {
      this.adapters.merges.delete(audioPath);
    }
  }

  /** Tell the upload path how a capture is cropped. */
  setCrop(audioPath: string, crop: { startSec?: number; endSec?: number } | undefined): void {
    if (crop && (crop.startSec !== undefined || crop.endSec !== undefined)) {
      this.adapters.crops.set(audioPath, crop);
    } else {
      this.adapters.crops.delete(audioPath);
    }
  }

  get location(): LocationProvider {
    return this.adapters.location;
  }

  get permissions(): PermissionsManager {
    return this.adapters.permissions;
  }

  get families(): FamilyRepository {
    return this.adapters.families;
  }

  get labels(): LabelRepository {
    return this.adapters.labels;
  }

  get context(): ContextRepository {
    return this.adapters.context;
  }

  get sightings(): SightingRepository {
    return this.adapters.sightings;
  }

  /**
   * Louder copies of captures, for listening to. Never the stored file — see
   * playback/NormalizedWav.ts.
   */
  readonly normalized = new NormalizedWav();

  get analysisCache(): AnalysisCache | undefined {
    return this.adapters.analysisCache;
  }

  get logs(): LogRepository | undefined {
    return this.adapters.logs;
  }

  /**
   * Push the app's own log.
   *
   * Never throws, and never reports through the capture sync's result: a
   * diagnostic upload that could turn a successful field sync into a failed one
   * would have inverted its own purpose. See sync/LogSync.ts.
   */
  async syncLogs(): Promise<LogSyncOutcome> {
    const logs = this.adapters.logs;
    if (!logs) return { sent: 0, error: "no log store" };
    // Anything still queued in memory goes down first, or the most recent
    // entries — the ones somebody is about to ask about — are the ones left
    // behind.
    await log.flush();
    try {
      return await new LogSync(logs, this.client).run();
    } catch (failure) {
      return {
        sent: 0,
        error: failure instanceof Error ? failure.message : String(failure),
      };
    }
  }

  /**
   * Pull back captures this phone no longer has.
   *
   * Additive only, and deliberately not part of Sync: sync is push-only because
   * the phone is the source of truth, and that rule is what stops a stale
   * server copy overwriting a field recording. A phone that has *lost* a
   * capture has no truth to contradict, which is the one case where reading
   * back is safe — and it is the case that already cost a real recording.
   */
  restoreFromServer(
    onProgress?: (done: number, total: number) => void,
  ): Promise<RestoreOutcome> {
    return new Restore(
      this.adapters.repository, this.client, new FileDownloader(),
    ).run(onProgress);
  }

  private readonly regions = new DeviceRegionLookup();

  /** Give old captures a region from their own GPS fix — see sync/BackfillRegions.ts. */
  backfillRegions(
    onProgress?: (done: number, total: number) => void,
  ): Promise<{ filled: number; unknown: number }> {
    return new BackfillRegions({
      repository: this.adapters.repository,
      regionFor: (fix) => this.regionFor(fix),
      homeRegion: () => this.currentSettings.homeRegion.trim() || undefined,
    }).run(onProgress);
  }

  /**
   * Do the backfill once, ever.
   *
   * Reverse geocoding needs a network on Android, so a run out of range fills
   * in nothing — and marking it done there would leave a corpus permanently
   * saying "no location" for want of one launch with signal. It is only
   * recorded as finished when no capture that *has* a fix is still missing a
   * region, which is the only definition of done that cannot lie.
   */
  async backfillRegionsOnce(): Promise<void> {
    if (this.currentSettings.regionsBackfilled) return;
    await this.backfillRegions();
    const stillMissing = (await this.adapters.repository.list()).some(
      (capture) =>
        !capture.region
        && capture.latitude !== undefined
        && capture.longitude !== undefined,
    );
    if (stillMissing) return;
    this.applySettings({ ...this.currentSettings, regionsBackfilled: true });
  }

  /**
   * Tell the server how precisely this recordist says where they were.
   *
   * The phone is what actually enforces it — nothing here decides what leaves,
   * SyncEngine does. This is so the server can refuse coordinates that reach it
   * anyway, from an older build or a client somebody else wrote.
   */
  private async publishLocationPrecision(settings: Settings): Promise<void> {
    if (!this.isEnrolled) return;
    try {
      await this.client.setLocationPrecision(
        settings.locationPrecision,
        settings.homeRegion.trim() || undefined,
        settings.censorCoords,
        settings.fuzzMiles,
      );
    } catch (failure) {
      // Already logged by the client. The local setting still holds, which is
      // the half that matters: the server never sees what is never sent.
      log.warn("location", "could not publish location precision", failure);
    }
  }

  /**
   * Which region a fix is in — resolved on the phone, never from an IP address.
   * See recording/RegionLookup.ts for why that distinction matters here.
   */
  regionFor(fix: Fix): Promise<string | undefined> {
    // Logged before it becomes "no region": for a contributor on region-only
    // precision this lookup is the entire location record, and a resolver
    // that always fails used to leave captures with no place and no trace.
    return this.regions.forFix(fix).catch((failure) => {
      log.warn("location", "could not resolve the region for a fix", failure);
      return undefined;
    });
  }

  /**
   * Pull every synced capture's analysis down, so the timeline works away from
   * the server.
   *
   * Not a violation of push-only sync: nothing here touches a capture row. It
   * fills a cache whose entire contents can be thrown away and re-fetched, and
   * it exists because the detections are wanted in a park — comparing a call
   * marked in June against one recorded five minutes ago is the whole reason to
   * carry them.
   */
  async prefetchAnalysis(
    onProgress?: (done: number, total: number) => void,
  ): Promise<PrefetchOutcome> {
    const cache = this.adapters.analysisCache;
    if (!cache) return { stored: 0, pending: 0, failed: 0, truncated: false, offline: false };
    return new PrefetchAnalysis(this.adapters.repository, cache, this.client).run(
      onProgress,
    );
  }

  /**
   * Look again at what is plugged in.
   *
   * Awaited before anything that depends on the answer, because the cheap
   * synchronous read is a snapshot — and the moment it matters most is the one
   * where a microphone has just been plugged in.
   */
  async refreshMicrophones(): Promise<void> {
    // The failure that makes this a no-op is the one worth seeing: a refresh
    // that silently failed leaves the stale list, at exactly the moment a
    // microphone was plugged in.
    await this.adapters.recorder.refreshInputs?.().catch((failure) =>
      log.warn("recorder", "could not refresh the microphone list", failure));
  }

  /**
   * Which microphone the *next* session should open with.
   *
   * Deliberately still a prediction — that is what opening a session needs. What
   * an already-open session is on is a different question with a different
   * answer, and it comes from `recorder.activeInput()`; domain/micState is where
   * the two are reconciled for anything shown to the recordist.
   */
  microphoneNow(): string {
    // An empty list resolves to the built-in mic on its own, which is the rule
    // this used to restate. Two statements of one default is how they drift.
    return resolveMic(
      this.currentSettings.micPriority,
      this.adapters.recorder.listInputs?.() ?? [],
    );
  }

  /**
   * Fold whatever is attached into the remembered list, and persist it.
   *
   * Called when the Settings screen opens, which is the only place the list is
   * read or arranged. Doing it on every launch would be tidier and would also
   * write to storage on a phone that is only being used to record.
   */
  rememberAttachedMics(): KnownMic[] {
    const attached = this.adapters.recorder.listInputs?.() ?? [];
    const merged = rememberMics(
      // First run after the update: carry over the single pin already in use, so
      // the list opens describing what the phone has been doing. Named properly
      // — "Current choice" said nothing about *which* microphone, which is the
      // one thing the row exists to say.
      this.currentSettings.micPriority.length > 0
        ? this.currentSettings.micPriority
        : seedFromPin(BUILTIN_MIC, attached),
      attached,
      new Date().toISOString(),
    );
    // Compared by content, not by length: repairing a label leaves the list
    // the same size, and a persist condition that only counts entries would
    // show the correction and never save it.
    const changed =
      JSON.stringify(merged) !== JSON.stringify(this.currentSettings.micPriority);
    if (changed) {
      this.applySettings({ ...this.currentSettings, micPriority: merged });
    }
    return merged;
  }

  /** Record what was witnessed. The WHY lives with the write, in Annotations.ts. */
  addContext(input: {
    uuid: string;
    captureUuid: string;
    /** Absent only on a capture confirmed to hold no calls. */
    labelUuid?: string;
    key: string;
    startSec?: number;
    endSec?: number;
  }): Promise<ContextRecord> {
    return this.annotations.addContext(input);
  }

  removeContext(event: ContextRecord): Promise<void> {
    return this.annotations.removeContext(event);
  }

  /** The served vocabulary — falls back to the CORE four until first fetch. */
  get trees(): TreeLayer | null {
    return this.currentTrees;
  }

  get scout(): ScoutLayer | null {
    return this.currentScout;
  }

  /** Mark a spot scouted: local first, pushed best-effort right after. */
  async addScoutVisit(kind: VisitKind, latitude: number, longitude: number,
                      outcome: VisitOutcome): Promise<ScoutVisit> {
    const visit: ScoutVisit = {
      uuid: newClientUuid(deviceRandomBytes),
      kind, latitude, longitude, outcome,
      visitedAt: new Date().toISOString(),
    };
    await this.adapters.scoutVisits.add(visit);
    void this.syncScoutVisits();
    return visit;
  }

  scoutVisitList(): Promise<ScoutVisit[]> {
    return this.adapters.scoutVisits.all();
  }

  /** Best spots inside a circle the recordist drew. Never throws — the
   *  circle was drawn in good faith, so failure is a note, not an error. */
  async scoutSpots(lat: number, lon: number, radiusM: number):
      Promise<{ spots: ScoutTarget[]; note?: string }> {
    try {
      const payload = await this.client.scoutSpots(lat, lon, radiusM);
      if (!payload) {
        return { spots: [], note: "the server has no spot search yet" };
      }
      const note = typeof payload.note === "string" ? payload.note : undefined;
      return { spots: scoutSpotsFromServer(payload), note };
    } catch {
      return { spots: [], note: "server unreachable" };
    }
  }

  /** Fire-and-forget like syncLogs; a failed push leaves rows pending. */
  async syncScoutVisits(): Promise<{ sent: number; error?: string }> {
    return new ScoutVisitSync(
      this.adapters.scoutVisits, () => this.client).run();
  }

  /** Same best-effort contract as refreshTrees. */
  async refreshScout(): Promise<ScoutLayer | null> {
    try {
      const payload = await this.client.scout();
      if (payload) {
        const layer = scoutLayerFromServer(payload);
        if (layer.targets.length > 0) {
          this.currentScout = layer;
          await this.store?.saveScout(layer);
        }
      }
    } catch {
      // Unreachable is not "no targets"; the held copy stands.
    }
    return this.currentScout;
  }

  /**
   * Re-fetch the tall-trees layer, best-effort like refreshConfig: a failed
   * fetch keeps the cached copy, and a server without the route (404 -> null)
   * keeps it too — offline in a park is exactly when the layer earns its keep.
   */
  async refreshTrees(): Promise<TreeLayer | null> {
    try {
      const payload = await this.client.trees();
      if (payload) {
        const layer = treeLayerFromGeojson(payload as { features?: never[] });
        if (layer.stands.length > 0) {
          this.currentTrees = layer;
          await this.store?.saveTrees(layer);
        }
      }
    } catch {
      // Unreachable is not "no trees"; the held copy stands.
    }
    return this.currentTrees;
  }

  get config(): FleetConfig {
    return this.currentConfig;
  }

  /**
   * Ask the server what build it is running, and whether it is behind this app.
   *
   * Best-effort like refreshConfig: a phone that cannot reach the server has
   * nothing to warn about, and failing here must not stop a sync.
   */
  async checkCompatibility(): Promise<Compatibility> {
    try {
      const health = await this.client.health();
      return compatibility(health.build);
    } catch {
      // Unreachable is not incompatible — but it is worth saying, and saying
      // quickly. A run that starts anyway spends up to thirty seconds per
      // capture discovering the same thing over and over, which is what "stuck
      // syncing" in the field actually was.
      return { reachable: false, serverBehind: false };
    }
  }

  /**
   * Re-read the fleet config, keeping the cached copy when nothing changed.
   *
   * Best-effort by design: a phone in a field with no signal must still be able
   * to label, so a failure here leaves the last known vocabulary in place
   * rather than emptying it.
   */
  async refreshConfig(): Promise<FleetConfig> {
    try {
      const fresh = await this.client.config(
        "en",
        this.currentConfig.version > 0 ? this.currentConfig.version : undefined,
      );
      if (fresh) {
        this.currentConfig = fresh;
        await this.store?.saveConfig(fresh);
      }
    } catch {
      // Keep what we have; the next launch tries again.
    }
    return this.currentConfig;
  }

  /** Record a field label. The revision-bump story lives in Annotations.ts. */
  addLabel(input: {
    uuid: string;
    captureUuid: string;
    callType: string;
    startSec: number;
    endSec: number;
    fromDetection?: boolean;
  }): Promise<LabelRecord> {
    return this.annotations.addLabel(input);
  }

  /** Set (or clear) which bird was watched making a call — see Annotations.ts. */
  setLabelCaller(label: LabelRecord, callerRole?: string): Promise<LabelRecord> {
    return this.annotations.setLabelCaller(label, callerRole);
  }

  /** Retract a label, and the context riding on it — see Annotations.ts. */
  removeLabel(label: LabelRecord): Promise<void> {
    return this.annotations.removeLabel(label);
  }

  /** Enter a spoken note against a capture — see Annotations.ts. */
  addDictation(dictation: NewDictation): Promise<DictationRecord> {
    return this.annotations.addDictation(dictation);
  }

  /** Forget a note and delete its audio — see Annotations.ts. */
  deleteDictation(uuid: string): Promise<void> {
    return this.annotations.deleteDictation(uuid);
  }

  /** Mark every note the process died in the middle of — see Annotations.ts. */
  reconcileDictations(): Promise<number> {
    return this.annotations.reconcileDictations();
  }

  get settings(): Settings {
    return this.currentSettings;
  }

  /** Spoken notes, for the screens that show and update them. */
  get dictations(): DictationRepository {
    return this.adapters.dictations;
  }

  get syncEngine(): SyncEngine {
    return this.engine;
  }

  get fieldServer(): FieldServerClient {
    return this.client;
  }

  get isEnrolled(): boolean {
    return this.client.deviceToken !== undefined;
  }

  /**
   * A client for a server, and the sync engine that runs on it.
   *
   * One site because there used to be two, and the second one quietly dropped
   * the label and context repositories: moving the app to a different server
   * stopped labels syncing until the next restart, with nothing on screen to say
   * so. Both are optional on SyncEngine, so the compiler had no opinion.
   */
  private connection(url: string, deviceToken?: string) {
    const client = new FieldServerClient(
      url,
      new XhrHttpClient(),
      deviceToken,
      currentBuild(),
    );
    return {
      client,
      engine: new SyncEngine({
        ...this.adapters,
        client,
        // Read at push time, not captured here: tightening the setting must
        // reach the captures already waiting in the queue.
        locationPrecision: () => this.currentSettings.locationPrecision,
        fuzzMiles: () => this.currentSettings.fuzzMiles,
      }),
    };
  }

  /**
   * Persist settings, rebuilding the client only if the server really moved.
   *
   * The device token belongs to the server that issued it, so changing the URL
   * drops it and forces a fresh enrollment.
   *
   * Pointing at a different server invalidates every remembered id, so the
   * captures have to be reset — which makes this destructive, and means it must
   * only ever run on a *committed* change. It used to be called on every
   * keystroke, so typing an address un-synced the whole library once per
   * character.
   */
  applySettings(settings: Settings): void {
    const serverChanged =
      settings.fieldServerUrl.trim() !== this.currentSettings.fieldServerUrl.trim();
    const renamed = settings.deviceLabel.trim() !== this.currentSettings.deviceLabel.trim();
    const personRenamed =
      settings.contributorName.trim() !== this.currentSettings.contributorName.trim()
      && settings.contributorName.trim().length > 0;
    const locationChanged =
      settings.locationPrecision !== this.currentSettings.locationPrecision
      || settings.homeRegion.trim() !== this.currentSettings.homeRegion.trim()
      || settings.fuzzMiles !== this.currentSettings.fuzzMiles
      // Was missing: toggling censoring alone never reached the server, so the
      // dashboard kept masking (or showing) from a stale answer.
      || settings.censorCoords !== this.currentSettings.censorCoords;
    const triggerChanged =
      settings.headsetTrigger !== this.currentSettings.headsetTrigger;
    const shutterChanged =
      settings.volumeShutter !== this.currentSettings.volumeShutter;
    const heartbeatChanged =
      settings.heartbeatListening !== this.currentSettings.heartbeatListening
      || settings.heartbeatRecording !== this.currentSettings.heartbeatRecording
      || settings.heartbeatListeningSeconds
        !== this.currentSettings.heartbeatListeningSeconds
      || settings.heartbeatRecordingSeconds
        !== this.currentSettings.heartbeatRecordingSeconds;
    this.currentSettings = settings;
    this.background("save settings", this.store?.saveSettings(settings));
    if (locationChanged) void this.publishLocationPrecision(settings);
    if (triggerChanged) this.claimHeadsetButton(settings.headsetTrigger);
    if (shutterChanged) this.applyVolumeShutter(settings.volumeShutter);
    if (heartbeatChanged) this.applyHeartbeat(settings);
    // Renaming the phone is worth a round-trip on its own: waiting for the next
    // sync would leave the fleet list saying "—" for a device you have already
    // named, which reads as the setting not having worked.
    if (renamed && !serverChanged && this.isEnrolled) {
      // Logged like the contributor rename below — the whole point of the
      // round-trip is that a silent no-op reads as the setting not working,
      // and a swallowed failure is a silent no-op with extra steps.
      void this.renameDevice(settings.deviceLabel.trim()).catch((failure) =>
        log.warn("identity", "could not rename device", failure));
    }
    // And the person, for the same reason and a worse one: the name field
    // seeded enrollment and then did nothing at all. Editing it after the first
    // sync changed a string on the phone while the fleet, the dashboard and
    // every capture already collected kept the old one — a setting that stops
    // working silently, which is the kind people stop trusting the rest of.
    if (personRenamed && !serverChanged && this.isEnrolled) {
      void this.ids
        .renameContributor(settings.contributorName.trim())
        .catch((failure) => log.warn("identity", "could not rename contributor", failure));
    }
    if (serverChanged) {
      ({ client: this.client, engine: this.engine } = this.connection(
        settings.fieldServerUrl,
      ));
      this.background("drop the device token", this.store?.saveDeviceToken(undefined));
      // The identity belonged to the server that issued the token, so it is now
      // a claim about a machine we are no longer talking to.
      this.background("drop the identity", this.ids.forget());
      this.background("forget capture sync state",
                      this.adapters.repository.forgetServerState());
      this.background("forget label sync state",
                      this.adapters.labels.forgetServerState());
      this.background("forget context sync state",
                      this.adapters.context.forgetServerState());
      // Sightings were missing from this list until now: SightingRepository has
      // had `forgetServerState` all along and nothing ever called it, so
      // pointing the app at a different server stranded every sighting against
      // a dead id.
      this.background("forget sighting sync state",
                      this.adapters.sightings.forgetServerState());
      this.background("forget scout visit sync state",
                      this.adapters.scoutVisits.forgetServerState());
      this.background("forget dictation sync state",
                      this.adapters.dictations.forgetServerState());
    }
  }

  get identity(): Identity | undefined {
    return this.ids.identity;
  }

  /**
   * Join the fleet — as a new contributor, or as another device of an existing
   * one when a claim code is set. The mechanism lives in Identity.ts.
   *
   * The claim code is cleared afterwards: it is single-purpose, and leaving a
   * secret sitting in a settings field invites it being reused on a third phone
   * that was meant to be someone else.
   */
  async enroll(): Promise<Identity> {
    const identity = await this.ids.enroll({
      enrollToken: this.currentSettings.enrollToken,
      contributorName: this.currentSettings.contributorName || "Unnamed recordist",
      label: this.currentSettings.deviceLabel || undefined,
      claimCode: this.currentSettings.claimCode || undefined,
    });
    if (this.currentSettings.claimCode) {
      this.currentSettings = { ...this.currentSettings, claimCode: "" };
      this.background("save settings", this.store?.saveSettings(this.currentSettings));
    }
    return identity;
  }

  /**
   * A fire-and-forget write, with its failure written down instead of lost.
   *
   * These used to be bare `void store?.save…()` calls, which made every one an
   * unhandled rejection waiting to happen — and worse, a setting that appeared
   * to take effect and then did not survive a restart, with nothing anywhere
   * saying why.
   */
  private background(what: string, work?: Promise<unknown>): void {
    void work?.catch((failure) => log.warn("store", `could not ${what}`, failure));
  }

  /** Re-read the identity from the server — see Identity.ts. */
  async refreshIdentity(): Promise<Identity | undefined> {
    if (!this.isEnrolled) return undefined;
    return this.ids.refresh(this.currentSettings.deviceLabel);
  }

  /** Push this handset's name, so the fleet list says "Pixel 10" not "—". */
  renameDevice(label: string): Promise<void> {
    return this.ids.renameDevice(label);
  }

  rotateClaimCode(): Promise<string> {
    return this.ids.rotateClaimCode();
  }
}
