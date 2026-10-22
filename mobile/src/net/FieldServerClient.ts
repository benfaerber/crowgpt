import type { FleetConfig } from "../domain/config";
import type { Identity } from "../domain/identity";
import type {
  AnalysisJob,
  AnalysisResult,
  DetectedCall,
  EnrolledDevice,
  ServerCapture,
  ServerContributor,
  ServerDevice,
  ServerDictation,
  ServerMedia,
} from "./serverTypes";
import { HttpError, type HttpClient } from "./HttpClient";
import { log } from "../app/Log";

/**
 * Typed client for the field server (`fieldserver/api.rest` is the contract).
 *
 * Deliberately dumb: it speaks HTTP and knows nothing about sync state or
 * retries. Deciding what to send, and what to do when it fails, is the sync
 * engine's job.
 */
/** Long enough for a slow LAN, short enough to answer a person standing in a park. */
const REACHABILITY_TIMEOUT_MS = 6_000;

export class FieldServerClient {
  private token?: string;

  constructor(
    private readonly baseUrl: string,
    private readonly http: HttpClient,
    token?: string,
    /**
     * Which build of the app is talking, reported on every request.
     *
     * Injected rather than imported: reading it means reading the Expo manifest,
     * and the net layer has to stay importable by a plain node test run.
     */
    private readonly build?: { version: number; commit: string },
  ) {
    this.token = token;
  }

  get deviceToken(): string | undefined {
    return this.token;
  }

  /**
   * Exchange the fleet enrollment secret for this device's bearer token.
   *
   * With a `claimCode` the phone joins an existing contributor instead of
   * becoming a new one — the difference between a second handset and a second
   * person. Without it, enrolling twice is how one recordist ends up owning a
   * fraction of their own corpus from each install.
   */
  async enroll(input: {
    enrollToken: string;
    contributorName: string;
    label?: string;
    claimCode?: string;
    locale?: string;
  }): Promise<EnrolledDevice> {
    const body = await this.json<{
      device_token: string;
      contributor: ServerContributor;
      device: ServerDevice;
      claim_code?: string;
    }>("POST", "/api/devices/register", {
      enroll_token: input.enrollToken,
      contributor_name: input.contributorName,
      label: input.label,
      claim_code: input.claimCode || undefined,
      platform: "android",
      locale: input.locale ?? "en",
    });
    this.token = body.device_token;
    return {
      deviceToken: body.device_token,
      identity: {
        contributorName: body.contributor.display_name,
        role: body.contributor.role,
        deviceId: body.device.id,
        deviceLabel: body.device.label ?? undefined,
        claimCode: body.claim_code,
      },
    };
  }

  /**
   * The fleet's served config, or null when the phone already has it.
   *
   * `since` is the version we hold; the server answers 304 to say "yours is
   * current", which keeps a launch-time check to one small request rather than
   * re-downloading a document that rarely changes.
   *
   * Unauthenticated by design — a phone needs the label set and the
   * instructions before it has enrolled.
   */
  async config(locale = "en", since?: number): Promise<FleetConfig | null> {
    const query = since === undefined ? "" : `&since=${since}`;
    return this.recording("GET", "/api/config", async () => {
      const response = await this.http.send({
        method: "GET",
        url: `${this.baseUrl}/api/config?locale=${encodeURIComponent(locale)}${query}`,
      });
      if (response.status === 304) return null;
      if (response.status >= 400) {
        throw new HttpError(response.status, "/api/config", response.body);
      }
      return JSON.parse(response.body) as FleetConfig;
    });
  }

  /** Idempotent on `clientUuid` — a replay carries the latest call type. */
  addLabel(
    captureId: number,
    input: {
      clientUuid: string;
      callType: string;
      species?: string;
      startSec?: number;
      endSec?: number;
      notes?: string;
      /**
       * Which vocabulary the labeller was shown.
       *
       * Sent rather than left for the server to infer, because this phone
       * labels offline against a cached list — the server's idea of "current"
       * when this arrives can be several versions past what was on screen.
       */
      configVersion?: number;
      /**
       * Which bird was watched making this call.
       *
       * Omitted rather than sent as null when absent: the server treats a
       * missing caller as "nobody looked" and must not be handed something that
       * could read as "nobody was there".
       */
      callerRole?: string;
    },
  ): Promise<{ id: number; call_type: string }> {
    return this.json("POST", `/api/captures/${captureId}/labels`, {
      client_uuid: input.clientUuid,
      config_version: input.configVersion,
      call_type: input.callType,
      species: input.species,
      start_sec: input.startSec,
      end_sec: input.endSec,
      notes: input.notes,
      caller_role: input.callerRole || undefined,
    });
  }

  /**
   * Set which bird was watched making a call, on a label the server already has.
   *
   * A separate request from creating the label because the two answers arrive at
   * different moments — the call type off a list, the caller off whatever was
   * visible — and folding them together would mean re-creating the label to
   * change the caller, which cascades away its context chips.
   */
  setLabelCaller(labelId: number, callerRole?: string): Promise<unknown> {
    return this.json("PATCH", `/api/labels/${labelId}`, {
      caller_role: callerRole ?? null,
    });
  }

  /** Idempotent on `clientUuid`. What a human witnessed, not what the bird said. */
  /**
   * Something seen near this recording but not during it.
   *
   * A separate route from `addContext` because it is separate evidence: context
   * is what a human witnessed while a call was made, and the calls x context
   * matrix is built from it. An after-the-fact sighting in there would confirm
   * whatever it was inferred from.
   */
  addSighting(
    captureId: number,
    input: {
      clientUuid: string;
      key: string;
      /** Signed seconds from the start of the recording. Required. */
      offsetSec: number;
      distanceM?: number;
      notes?: string;
    },
  ): Promise<{ id: number; key: string }> {
    return this.json("POST", `/api/captures/${captureId}/sightings`, {
      client_uuid: input.clientUuid,
      key: input.key,
      offset_sec: input.offsetSec,
      distance_m: input.distanceM,
      notes: input.notes,
    });
  }

  /**
   * Tell the server which captures this one replaced.
   *
   * Only parts that had already synced are named: one that never reached the
   * server was folded in locally and travels inside the joined audio, so there
   * is nothing up there to supersede. That is why the route accepts a single
   * part — a three-way merge where one part had synced has exactly one row to
   * point at.
   *
   * `offsetMs` comes from the assembled audio rather than from the durations in
   * the database, because it is what a label made against a part has to be
   * moved by, and metadata that disagrees with the file would move it wrongly.
   */
  recordMerge(
    captureId: number,
    parts: { captureId: number; offsetMs: number }[],
  ): Promise<{ merged_capture_id: number; parts: unknown[] }> {
    return this.json("POST", `/api/captures/${captureId}/merge`, {
      parts: parts.map((p) => ({ capture_id: p.captureId, offset_ms: p.offsetMs })),
    });
  }

  /**
   * Push a batch of the phone's own log lines.
   *
   * Answers with the client uuids the server now holds, so a batch that only
   * partly landed can be marked precisely — a count would leave the phone
   * either re-sending forever or losing the tail.
   */
  pushLogs(entries: {
    clientUuid: string;
    at: string;
    level: string;
    tag: string;
    message: string;
    detail?: unknown;
  }[]): Promise<{ accepted: string[]; rejected: { client_uuid: string | null }[] }> {
    return this.json("POST", "/api/logs", {
      entries: entries.map((entry) => ({
        client_uuid: entry.clientUuid,
        at: entry.at,
        level: entry.level,
        tag: entry.tag,
        message: entry.message,
        detail: entry.detail,
      })),
    });
  }

  /**
   * Tell the server how precisely this recordist says where they were.
   *
   * Not what stops coordinates being sent — the phone does that, and a promise
   * kept there is a fact rather than something to trust. This lets the server
   * refuse any that reach it anyway.
   */
  setLocationPrecision(
    precision: string,
    region?: string,
    censorCoords?: boolean,
    fuzzMiles?: number,
  ): Promise<{ location_precision: string; region: string | null;
               censor_coords?: number; fuzz_miles?: number }> {
    return this.json("PATCH", "/api/me/location-precision", {
      location_precision: precision,
      region,
      // Sent so the dashboard masks the same way the phone does. Omitting it
      // leaves the server's value alone rather than clearing it, so an older
      // client cannot unmask somebody by not mentioning the field.
      censor_coords: censorCoords,
      fuzz_miles: fuzzMiles,
    });
  }

  addContext(
    captureId: number,
    input: {
      clientUuid: string;
      /**
       * Which call this was the situation for.
       *
       * Optional only for a capture confirmed to hold no calls — there is
       * nothing to attach to, and that recording is the control group.
       */
      labelId?: number;
      key: string;
      startSec?: number;
      endSec?: number;
      notes?: string;
      /** The vocabulary this situation was chosen from. See addLabel. */
      configVersion?: number;
    },
  ): Promise<{ id: number; key: string }> {
    return this.json("POST", `/api/captures/${captureId}/context`, {
      client_uuid: input.clientUuid,
      label_id: input.labelId,
      key: input.key,
      start_sec: input.startSec,
      end_sec: input.endSec,
      notes: input.notes,
      config_version: input.configVersion,
    });
  }

  async deleteContext(eventId: number): Promise<void> {
    await this.json("DELETE", `/api/context/${eventId}`);
  }

  async deleteLabel(labelId: number): Promise<void> {
    await this.json("DELETE", `/api/labels/${labelId}`);
  }

  /** Who this device belongs to, and every handset that person carries. */
  me(): Promise<{
    contributor: ServerContributor;
    device: ServerDevice;
    devices: ServerDevice[];
  }> {
    return this.json("GET", "/api/me");
  }

  renameDevice(deviceId: number, label: string): Promise<ServerDevice> {
    return this.json("PATCH", `/api/devices/${deviceId}`, { label });
  }

  renameContributor(displayName: string): Promise<ServerContributor> {
    return this.json("PATCH", "/api/me", { display_name: displayName });
  }

  /** Mint a fresh code for adding another phone, invalidating the previous one. */
  async rotateClaimCode(): Promise<string> {
    const body = await this.json<{ claim_code: string }>("POST", "/api/me/claim-code");
    return body.claim_code;
  }

  /** Idempotent on `clientUuid`. Families belong to the device that creates them. */
  createFamily(input: {
    clientUuid: string;
    name: string;
    color?: string;
    notes?: string;
  }): Promise<{ id: number; name: string; color: string | null }> {
    return this.json("POST", "/api/families", {
      client_uuid: input.clientUuid,
      name: input.name,
      color: input.color,
      notes: input.notes,
    });
  }

  /**
   * Apply an edit to a capture the server already has.
   *
   * The create call carries these fields too, but only ever *once*. Tagging a
   * family back at the desk is the common case, and without this the change
   * re-synced forever without landing.
   */
  updateCapture(
    captureId: number,
    input: {
      name?: string;
      keep?: boolean;
      familyId?: number;
      notes?: string;
      locationName?: string;
      latitude?: number;
      longitude?: number;
      /** How coarse the coordinates are, in miles — sent when they are snapped. */
      coordFuzzMiles?: number;
      region?: string;
      observerRole?: string;
      behaviorGuess?: string;
      distanceBand?: string;
      adultCount?: number;
      juvenileCount?: number;
      unagedCount?: number;
      /** True marks the recording as holding no crow calls; false takes it back. */
      silent?: boolean;
      nothingToLabel?: boolean;
    },
  ): Promise<ServerCapture> {
    return this.json<ServerCapture>("PATCH", `/api/captures/${captureId}`, {
      name: input.name,
      keep: input.keep,
      family_id: input.familyId,
      notes: input.notes,
      location_name: input.locationName,
      latitude: input.latitude,
      longitude: input.longitude,
      coord_fuzz_miles: input.coordFuzzMiles,
      region: input.region,
      observer_role: input.observerRole,
      behavior_guess: input.behaviorGuess,
      distance_band: input.distanceBand,
      adult_count: input.adultCount,
      juvenile_count: input.juvenileCount,
      unaged_count: input.unagedCount,
      silent: input.silent,
      nothing_to_label: input.nothingToLabel,
    });
  }

  /**
   * Every capture this contributor has on the server.
   *
   * The read side of a push-only sync. Used only by restore — a phone that has
   * lost its local store, where there is no local truth for the server to
   * contradict.
   */
  listCaptures(): Promise<ServerCapture[]> {
    return this.json<ServerCapture[]>("GET", "/api/captures");
  }

  /** What was uploaded for a capture, so a restore knows what to fetch. */
  captureMedia(captureId: number): Promise<ServerMedia[]> {
    return this.json<ServerMedia[]>("GET", `/api/captures/${captureId}/media`);
  }

  /** Where the stored bytes live, for a downloader that streams to a file. */
  /**
   * Where a capture's audio can be fetched.
   *
   * `asWav` asks the server to render one, because this app parses RIFF
   * headers directly in three places — the waveform, the playback boost and
   * the crop before upload — and the server now stores FLAC. Without it a
   * restored capture plays but has no trace and no boost, failing quietly
   * three times over. A server too old to know the parameter ignores it and
   * serves the WAV it has.
   */
  mediaUrl(mediaId: number, asWav = false): string {
    return this.url(`/api/media/${mediaId}/raw${asWav ? "?format=wav" : ""}`);
  }

  /** Headers a plain downloader needs to be let in. */
  authHeadersFor(): Record<string, string> {
    return this.standardHeaders();
  }

  /** Idempotent on `clientUuid` — a replay returns the original capture. */
  createCapture(input: {
    clientUuid: string;
    name?: string;
    /** Marked a real observation rather than test material. */
    keep?: boolean;
    latitude?: number;
    longitude?: number;
    /** How coarse the coordinates are, in miles — sent when they are snapped. */
    coordFuzzMiles?: number;
    /** "Utah, US" — what a capture says about place once coordinates are gone. */
    region?: string;
    locationName?: string;
    recordedAt?: string;
    durationSec?: number;
    notes?: string;
    familyId?: number;
    /** The app build that recorded it — not the one uploading it now. */
    appVersion?: number;
    appCommit?: string;
    /** "auto" when the idle trigger started the recording, else absent. */
    trigger?: "auto";
    observerRole?: string;
    behaviorGuess?: string;
    /**
     * Which span of the recording these bytes are.
     *
     * Sent at create because it describes what is being uploaded. The server
     * reports `duration_sec` for the whole recording, so without this it holds
     * twelve seconds of audio labelled ninety and nothing says why.
     */
    cropStartSec?: number;
    cropEndSec?: number;
    distanceBand?: string;
    adultCount?: number;
    juvenileCount?: number;
    unagedCount?: number;
  }): Promise<ServerCapture> {
    return this.json<ServerCapture>("POST", "/api/captures", {
      client_uuid: input.clientUuid,
      name: input.name,
      keep: input.keep,
      latitude: input.latitude,
      longitude: input.longitude,
      coord_fuzz_miles: input.coordFuzzMiles,
      region: input.region,
      location_name: input.locationName,
      recorded_at: input.recordedAt,
      duration_sec: input.durationSec,
      notes: input.notes,
      family_id: input.familyId,
      app_version: input.appVersion,
      app_commit: input.appCommit,
      trigger: input.trigger,
      observer_role: input.observerRole,
      behavior_guess: input.behaviorGuess,
      crop_start_sec: input.cropStartSec,
      crop_end_sec: input.cropEndSec,
      distance_band: input.distanceBand,
      adult_count: input.adultCount,
      juvenile_count: input.juvenileCount,
      unaged_count: input.unagedCount,
    });
  }

  /**
   * Idempotent on `clientUuid`. The returned `bytes` is authoritative for where
   * an interrupted upload resumes — trust it over any local guess, since the
   * server is the one that knows what actually landed.
   */
  createMedia(
    captureId: number,
    input: {
      clientUuid: string;
      /** 'audio' is the analyzed track; 'video' rides along as context. */
      kind?: "audio" | "video";
      format?: string;
      sampleRate?: number;
      channels?: number;
      /**
       * Which microphone recorded these bytes, e.g. "BUILTIN_MIC". Provenance
       * that cannot be recovered later: nothing in a WAV says it came through a
       * Bluetooth headset, and a clip that did is worth much less as training
       * data.
       */
      inputDevice?: string;
      inputHonoured?: boolean;
      /** Seconds at the head of the file recorded before the button was pressed. */
      preRollSec?: number;
    },
  ): Promise<ServerMedia> {
    return this.json<ServerMedia>("POST", `/api/captures/${captureId}/media`, {
      client_uuid: input.clientUuid,
      kind: input.kind ?? "audio",
      format: input.format ?? "wav",
      sample_rate: input.sampleRate ?? 48000,
      channels: input.channels ?? 1,
      input_device: input.inputDevice,
      input_honoured: input.inputHonoured,
      pre_roll_sec: input.preRollSec,
    });
  }

  /** Upload one chunk. The server finalizes once `offset + chunk.length` reaches `total`. */
  /**
   * A ranged PUT of one chunk. Shared by media and dictations.
   *
   * One implementation because the subtlety is not the header: the server
   * compresses on the final chunk and returns the SMALLER byte count, so only
   * `upload_state === "complete"` may be trusted to end a loop. A second copy of
   * this would get that wrong quietly, and the symptom is an upload that writes
   * past the end of a finished file.
   */
  private async putRanged<T>(
    path: string,
    chunk: Uint8Array,
    offset: number,
    total: number,
  ): Promise<T> {
    const end = offset + chunk.length - 1;
    return this.recording("PUT", path, async () => {
      const response = await this.http.sendBytes({
        method: "PUT",
        url: this.url(path),
        headers: {
          ...this.standardHeaders(),
          "Content-Type": "application/octet-stream",
          "Content-Range": `bytes ${offset}-${end}/${total}`,
        },
        bytes: chunk,
      });
      return this.parse<T>(response.status, response.body, path);
    });
  }

  uploadChunk(
    mediaId: number,
    chunk: Uint8Array,
    offset: number,
    total: number,
  ): Promise<ServerMedia> {
    return this.putRanged<ServerMedia>(
      `/api/media/${mediaId}`, chunk, offset, total);
  }

  /**
   * Register a spoken note against a capture, or resume the one already there.
   *
   * Its own route rather than a media kind: the server keeps dictations in a
   * separate table and directory precisely so nothing that walks the media
   * store can pick up a human voice track as bird audio.
   */
  createDictation(captureId: number, input: {
    clientUuid: string;
    recordedAt?: string;
    durationSec?: number;
    sampleRate?: number;
    channels?: number;
    format?: string;
    locale?: string;
  }): Promise<ServerDictation> {
    return this.json<ServerDictation>(
      "POST", `/api/captures/${captureId}/dictations`, {
      client_uuid: input.clientUuid,
      recorded_at: input.recordedAt,
      duration_sec: input.durationSec,
      sample_rate: input.sampleRate,
      channels: input.channels,
      format: input.format,
      locale: input.locale,
    });
  }

  /**
   * What the server holds for this capture, transcripts included.
   *
   * The one thing that comes back down. Sync is push-only because a stale
   * server copy must never overwrite a field recording — but a transcript is
   * DERIVED on the server and the phone has no opinion about it, exactly like
   * the detections `PrefetchAnalysis` already pulls. There is nothing to
   * contradict, so nothing to lose.
   */
  listDictations(captureId: number): Promise<ServerDictation[]> {
    return this.json<ServerDictation[]>(
      "GET", `/api/captures/${captureId}/dictations`);
  }

  uploadDictationChunk(
    dictationId: number,
    chunk: Uint8Array,
    offset: number,
    total: number,
  ): Promise<ServerDictation> {
    return this.putRanged<ServerDictation>(
      `/api/dictations/${dictationId}`, chunk, offset, total);
  }

  /**
   * Idempotent on `clientUuid`, and a replay carries the latest body — the
   * recordist may well have reworded the note between a failed push and the
   * retry, and the newer text is the one worth keeping.
   */
  addObservation(
    captureId: number,
    input: { clientUuid: string; body: string; source?: "typed" | "voice" },
  ): Promise<{ id: number; body: string }> {
    return this.json("POST", `/api/captures/${captureId}/observations`, {
      client_uuid: input.clientUuid,
      body: input.body,
      source: input.source ?? "typed",
    });
  }

  requestAnalysis(captureId: number): Promise<AnalysisJob> {
    return this.json<AnalysisJob>("POST", `/api/captures/${captureId}/analyze`);
  }

  job(jobId: number): Promise<AnalysisJob> {
    return this.json<AnalysisJob>("GET", `/api/jobs/${jobId}`);
  }

  /**
   * The endpoint answers with the whole analysis result — duration, waveform,
   * reliability and the calls — or `{capture_id, calls: []}` when nothing has
   * been analyzed yet. Only the calls are wanted here, and unwrapping in one
   * place keeps every caller from having to know that.
   */
  async analysis(captureId: number): Promise<AnalysisResult> {
    const result = await this.json<AnalysisResult>(
      "GET",
      `/api/captures/${captureId}/calls`,
    );
    return {
      capture_id: captureId,
      duration: result?.duration,
      waveform: Array.isArray(result?.waveform) ? result.waveform : [],
      calls: Array.isArray(result?.calls) ? result.calls : [],
    };
  }

  async calls(captureId: number): Promise<DetectedCall[]> {
    return (await this.analysis(captureId)).calls;
  }

  /**
   * Is the server there, and what is it running?
   *
   * Short timeout on purpose: this is the question whose *failure* is the
   * answer, and every second spent waiting for it is a second before a phone
   * in a field can be told there is no point.
   */
  health(): Promise<{
    ok: boolean;
    config_version: number;
    /** Absent on a server too old to publish one, which is itself the answer. */
    build?: { version: number; commit: string; dirty: boolean; wire?: number };
  }> {
    return this.json("GET", "/api/health", undefined, REACHABILITY_TIMEOUT_MS);
  }

  /**
   * The published tall-trees layer, or null when the server has none.
   *
   * 404 is a first-class answer — the layer is optional and older servers
   * don't have the route — so it must not be recorded as a failure or shown
   * to anyone; the map simply doesn't offer the toggle.
   */
  async trees(): Promise<{ features?: unknown[] } | null> {
    try {
      return await this.json<{ features?: unknown[] }>("GET", "/api/trees");
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) return null;
      throw error;
    }
  }

  /** Record a scouting mark; idempotent on client_uuid like every push. */
  async addScoutVisit(visit: {
    uuid: string; kind: string; latitude: number; longitude: number;
    outcome: string; note?: string; visitedAt: string;
  }): Promise<{ id: number }> {
    return this.json<{ id: number }>("POST", "/api/scout/visits", {
      client_uuid: visit.uuid,
      kind: visit.kind,
      latitude: visit.latitude,
      longitude: visit.longitude,
      outcome: visit.outcome,
      note: visit.note,
      visited_at: visit.visitedAt,
    });
  }

  /** Best scored cells inside a circle drawn on the map. Null when the
   *  server predates the route — the map quietly says so. */
  async scoutSpots(lat: number, lon: number, radiusM: number):
      Promise<{ spots?: unknown[]; note?: string } | null> {
    try {
      return await this.json<{ spots?: unknown[]; note?: string }>(
        "GET", `/api/scout/spots?lat=${lat}&lon=${lon}`
        + `&radius_m=${Math.round(radiusM)}`);
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) return null;
      throw error;
    }
  }

  /** The scouting layer, or null when none is published — same contract as trees(). */
  async scout(): Promise<{ targets?: unknown[]; owls?: unknown[] } | null> {
    try {
      return await this.json<{ targets?: unknown[]; owls?: unknown[] }>(
        "GET", "/api/scout");
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) return null;
      throw error;
    }
  }

  private json<T>(
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    body?: unknown,
    timeoutMs?: number,
  ): Promise<T> {
    return this.recording(method, path, async () => {
      const response = await this.http.send({
        method,
        url: this.url(path),
        headers: {
          ...this.standardHeaders(),
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        timeoutMs,
      });
      return this.parse<T>(response.status, response.body, path);
    });
  }

  /**
   * Write down every request that did not work.
   *
   * Here rather than at each call site, because the call sites are where it
   * gets forgotten. "Send logs" failed in airplane mode and left nothing in the
   * log — which is the one failure a log cannot afford to miss, and the
   * complaint that produced this: the failures are the entries worth having.
   *
   * Both kinds are caught: a status the server refused, and a request that
   * never reached one. The entry is written locally and goes up on the next
   * successful push, so a bad afternoon out of range is readable afterwards.
   */
  private async recording<T>(
    method: string,
    path: string,
    attempt: () => Promise<T>,
  ): Promise<T> {
    try {
      return await attempt();
    } catch (failure) {
      log.warn("net", `${method} ${path} failed`, {
        status: failure instanceof HttpError ? failure.status : undefined,
        error: failure instanceof Error ? failure.message : String(failure),
      });
      throw failure;
    }
  }

  private parse<T>(status: number, body: string, path: string): T {
    if (status < 200 || status >= 300) throw new HttpError(status, path, body);
    try {
      return JSON.parse(body) as T;
    } catch {
      throw new HttpError(status, path, `expected JSON, got: ${body.slice(0, 200)}`);
    }
  }

  /**
   * Sent on every request, upload chunks included.
   *
   * The build goes on all of them rather than on a report-my-version route, so
   * the server's record of what each phone is running cannot drift out of date
   * while the phone is otherwise syncing happily. That combination — busy phone,
   * stale bundle — is what makes a fix that shipped look like a fix that failed.
   */
  private standardHeaders(): Record<string, string> {
    return {
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      ...(this.build && this.build.version > 0
        ? {
            "X-App-Version": String(this.build.version),
            "X-App-Commit": this.build.commit,
          }
        : {}),
    };
  }

  private url(path: string): string {
    return `${this.baseUrl.replace(/\/+$/, "")}${path}`;
  }
}
