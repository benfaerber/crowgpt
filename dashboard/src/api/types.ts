/**
 * The shapes `/api/fleet/*` returns.
 *
 * Deliberately snake_case and deliberately *not* shared with the field app.
 * They look adjacent but describe different things: the app models a capture it
 * owns and is responsible for syncing — crop spans, revisions, upload offsets —
 * while these are read-model rows with join counts the app has no concept of.
 * The two clients speak to disjoint endpoints, so a shared type would be a
 * coupling with nothing behind it.
 */

export type ContributorRole = "contributor" | "operator" | "admin";
export type CaptureStatus = "recording" | "uploaded" | "analyzing" | "analyzed";

export interface FleetSummary {
  contributors: number;
  devices: number;
  captures: number;
  capture_statuses: Record<string, number>;
  jobs: Record<string, number>;
  media_bytes: number;
  media_complete: number;
  /** Captures the recordist marked real; the rest is seeded and test material. */
  kept_captures: number;
  detected_calls: number;
  labels: number;
  observations: number;
  unlabelled_captures: number;
  config_version: number;
}

export interface FleetCapture {
  id: number;
  name: string | null;
  contributor_name: string | null;
  device_label: string | null;
  status: CaptureStatus;
  recorded_at: string | null;
  created_at: string;
  duration_sec: number | null;
  latitude: number | null;
  longitude: number | null;
  /** "Utah, US" — what a capture says about place when coordinates are withheld. */
  region?: string | null;
  /** The owner's choice: exact | fuzzed | region. */
  location_precision?: string | null;
  /** 1 when recorded coordinates must not be displayed. */
  censor_coords?: number | null;
  location_name: string | null;
  notes: string | null;
  keep: number | null;
  /**
   * What the recordist was to these crows — a key from `observer_roles`.
   * Null means nobody said, which is not the same as "stranger".
   */
  observer_role: string | null;
  /** Roughly how far the bird was — the confound in any cross-site comparison. */
  distance_band: string | null;
  /** Who was there. Unaged is birds seen but too far to age, not a guess. */
  adult_count: number | null;
  juvenile_count: number | null;
  unaged_count: number | null;
  /** Set when a human confirmed the recording holds no crow calls. */
  silent_confirmed_at: string | null;
  /** Which family — the same birds, the same territory, across months. */
  family_id: number | null;
  /**
   * The app build that recorded it, as a commit count and a hash.
   *
   * Provenance for "why does this batch look wrong": a bug shipped on a known
   * build has a known blast radius, and without this the answer is every
   * capture or none.
   */
  app_version: number | null;
  app_commit: string | null;
  /** The recordist's hypothesis. Never ground truth — see the field app. */
  behavior_guess: string | null;
  /**
   * Which span of the recording the stored audio is. Null means untrimmed.
   * `duration_sec` stays the length of what was recorded.
   */
  crop_start_sec: number | null;
  crop_end_sec: number | null;
  call_count: number | null;
  label_count: number | null;
  observation_count: number | null;
  media_bytes: number | null;
  /** 0004's calibrated axis (~2.5 dB ≈ 0.19 confidence). */
  band_snr_db: number | null;
  /** Set once quality was measured — so a null SNR above can be told apart:
   *  never measured, versus measured and unmeasurable (merged capture). */
  quality_measured_at: string | null;
}

export interface Contributor {
  id: number;
  public_uuid: string;
  display_name: string;
  role: ContributorRole;
  status: "active" | "suspended";
  device_count: number;
  device_labels: string | null;
  capture_count: number;
  label_count: number;
  last_seen_at: string | null;
}

export interface Device {
  id: number;
  label: string | null;
  contributor_id: number | null;
  display_name: string | null;
  platform: string | null;
  capture_count: number;
  label_count: number;
  last_seen_at: string | null;
  revoked_at: string | null;
  /**
   * Which build of the app this handset last called in with, as a commit count.
   *
   * Null for one that has never reported — an app old enough to predate the
   * header, which is exactly the app worth knowing about.
   */
  app_version: number | null;
  app_commit: string | null;
}

export interface Family {
  id: number;
  name: string;
  color: string | null;
  notes: string | null;
  contributor_name: string | null;
  capture_count: number;
  call_count: number;
  observation_count: number;
  first_heard: string | null;
  last_heard: string | null;
  /** Centroid of its captures — what makes a family a *place*. */
  latitude: number | null;
  longitude: number | null;
}

export interface CallType {
  species: string;
  call_type: string | null;
  n: number;
  mean_confidence: number | null;
}

export interface FamilyDetail {
  family: Family;
  captures: FleetCapture[];
  call_types: CallType[];
}

export interface Media {
  id: number;
  kind: "audio" | "video";
  format: string;
  sample_rate: number | null;
  channels: number | null;
  /** Which microphone recorded it — null on anything predating mic pinning. */
  input_device: string | null;
  input_honoured: number | null;
  /** Seconds of ring buffer prepended — audio from before the button. */
  pre_roll_sec: number | null;
  bytes: number;
  sha256: string | null;
  upload_state: "pending" | "partial" | "complete";
  uploaded_at: string | null;
}

export interface DetectedCall {
  start_sec: number;
  end_sec: number;
  species: string;
  scientific_name: string | null;
  call_type: string | null;
  confidence: number | null;
  /** How sure the crow head was, as distinct from the species detector. */
  crow_conf: number | null;
  /**
   * Sub-threshold, offered for a human to rule on rather than counted.
   *
   * Rendering one identically to a confirmed detection is exactly the loop
   * experiment 0004 exists to break — the faint awkward calls are the ones the
   * training set most needs, and they are the ones a confident-looking table
   * quietly launders into fact.
   */
  candidate: number | null;
  /**
   * Other call types the head also heard in this span.
   *
   * A region can hold more than one call — capture 104 has an adult cawing
   * over a fledgling's begging — and until 0018 the analyzer took argmax and
   * dropped the rest. Empty on a confident single call, and on every row
   * analysed before that migration.
   */
  alternates?: { call_type: string; confidence: number }[];
  /**
   * Whether those alternates are independent probabilities or a runner-up.
   *
   * A one-vs-rest head's classes do not compete, so a second high score means
   * it heard two things. A softmax's do, so the same number means it was torn
   * between two readings of one thing. Both kinds of head are live — only the
   * American Crow head has been retrained — so the claim has to travel with
   * the numbers.
   */
  multi_label?: boolean;
}

export interface Label {
  id: number;
  species: string;
  call_type: string;
  start_sec: number | null;
  end_sec: number | null;
  label_source: string;
  /** The labeller's own words about this call, distinct from the capture's. */
  notes: string | null;
  /** Which vocabulary version this judgement was chosen from. */
  config_version: number | null;
  created_at: string | null;
}

/**
 * Prose a model wrote about the recording, or about one span of it.
 *
 * A guess of the same standing as a detection, never as testimony — both null
 * spans mean the recording as a whole. Keyed on the span rather than a label so
 * it survives the label being re-answered.
 */
/**
 * A spoken field note and a machine's reading of it.
 *
 * The middle trust tier, and the reason it exists as its own type: the words
 * are the recordist's and the spelling is a guess. `confirmed_at` is the line —
 * before it, a transcript is what a model heard; after it, a human has read the
 * words and they are also an observation.
 */
export interface Dictation {
  id: number;
  duration_sec: number | null;
  bytes: number;
  upload_state: string;
  recorded_at: string | null;
  transcript: string | null;
  transcript_model: string | null;
  mean_logprob: number | null;
  transcribed_at: string | null;
  confirmed_at: string | null;
  observation_id: number | null;
}

export interface AiDescription {
  id: number;
  start_sec: number | null;
  end_sec: number | null;
  description: string;
  model: string | null;
  written_at: string;
}

export interface Observation {
  id: number;
  body: string;
  source: string;
  locale: string | null;
  created_at: string;
  updated_at: string;
}

/** What the worker produced. The waveform was always here — just never drawn. */
export interface Analysis {
  capture_id: number;
  calls: DetectedCall[];
  duration?: number;
  /** Peak envelope, 0..1, computed once by the worker and stored. */
  waveform?: number[];
  model_version?: string;
  /** Per-head calibration. Stored and served; nothing surfaces it yet. */
  reliability?: Record<string, unknown>;
}

/**
 * Measured audio quality — how hard the recording was to hear. Written by the
 * worker at analysis time; measurements, never judgements. Null on a capture
 * the worker has not reached.
 */
export interface CaptureQuality {
  capture_id: number;
  media_id: number;
  /** Null when there is no quiet signal to measure against — a merged capture's
   *  silence gaps put digital zero in the quiet percentile. Not "unmeasured". */
  band_snr_db: number | null;
  /** p10 dBFS in 0–300 Hz — rumble, which masks nothing a crow says. */
  noise_floor_low_dbfs: number;
  /** p10 dBFS in 800–4000 Hz — what actually masks a call (experiment 0008). */
  noise_floor_band_dbfs: number;
  peak_dbfs: number;
  rms_dbfs: number;
  clipped_samples: number;
  /** Clipped runs grouped by 50 ms — 195 samples can be two knocks (0009). */
  clip_events: number;
  measured_at: string;
}

export interface CaptureDetail {
  capture: FleetCapture;
  media: Media[];
  analysis: Analysis | null;
  quality: CaptureQuality | null;
  labels: Label[];
  observations: Observation[];
  context: ContextEvent[];
  /** Separate from `context` on purpose — see the Sighting docstring. */
  sightings: Sighting[];
  /** Machine-written, and a separate key so it cannot be rendered as testimony. */
  ai_descriptions: AiDescription[];
  dictations: Dictation[];
}

/** The fleet's served vocabulary — the single source of truth for call colours. */
export interface FleetConfig {
  version: number;
  locale: string;
  core_classes: string[];
  core_colors: Record<string, string>;
  labels: { key: string; core: string; text: string }[];
  contexts: { key: string; category: string; text: string }[];
  /**
   * What the recordist was *to these crows*. Served precisely so that the phone
   * and the dashboard cannot disagree about what "feeder" means — and the
   * dashboard did not read it, so it printed the raw key while the phone showed
   * the sentence. The two are not synonyms: `known_passerby` reads as "known
   * passerby", which sounds like a bystander, when it means "They know me, no
   * food". Optional because a server one config version behind may not send it.
   */
  observer_roles?: { key: string; text: string }[];
}

/** Witnessed situations attached to a capture — the other axis. */
export interface ContextEvent {
  id: number;
  /** The call this was the situation for. Context is per call, not per capture. */
  label_id: number | null;
  key: string;
  start_sec: number | null;
  end_sec: number | null;
  notes: string | null;
  created_at: string;
}

export interface CallContextMatrix {
  /** Situations witnessed on recordings confirmed to hold no calls. */
  silent_contexts?: { key: string; captures: number }[];
  silent_captures?: number;
  /**
   * One row per (context, call type, **species**). Species is part of the key:
   * "alarm call" is a different vocalisation in an American Crow and a hooded
   * crow, and averaging them describes neither bird.
   */
  pairs: {
    context_key: string;
    call_type: string;
    species: string;
    n: number;
    captures: number;
  }[];
  contexts: { key: string; captures: number; labelled_calls: number }[];
  /** Tagged captures with no confirmed calls — recordings still unread. */
  contexts_awaiting_labels: number;
  /** True when only captures marked as real observations were counted. */
  kept_only: boolean;
}

export interface LabelTotal {
  call_type: string;
  species: string;
  n: number;
}

/**
 * Something seen near a recording but not during it — a lead, not ground truth.
 *
 * Kept apart from context events by construction, not by convention: they never
 * share a table, a route key, or a panel, so an inferred sighting cannot end up
 * confirming whatever it was inferred from.
 */
export interface Sighting {
  id: number;
  capture_id: number;
  key: string;
  /** Signed seconds from the start of the recording; negative is before it. */
  offset_sec: number;
  distance_m: number | null;
  notes: string | null;
  created_at: string;
}

export type LogLevel = "debug" | "info" | "warn" | "error";

/**
 * One line the field app wrote about itself.
 *
 * Two clocks on purpose: `at` is the phone's, `received_at` is ours. A handset
 * that was offline for a week pushes week-old lines, and the gap between them
 * is itself diagnostic.
 */
export interface DeviceLog {
  id: number;
  device_id: number;
  device_label: string | null;
  display_name: string | null;
  client_uuid: string;
  at: string;
  received_at: string;
  level: LogLevel;
  /** Which part of the app spoke: recorder, sync, db, app, console. */
  tag: string;
  message: string;
  /** JSON as text — stacks, ids, sizes. Shape differs per subsystem. */
  detail: string | null;
  app_version: number | null;
  app_commit: string | null;
}

/**
 * A label whose vocabulary moved after it was made.
 *
 * Answerable only because each label records which version of the vocabulary
 * it was chosen from — see the field server's relabel_queue.
 */
export interface RelabelRow {
  id: number;
  capture_id: number;
  call_type: string;
  species: string;
  created_at: string;
  config_version: number;
  contributor_name: string | null;
  /** In words: retired, reintroduced, or gone entirely. */
  why: string;
}

/** One stage of a training run, as `crowgpt.progress.Run` records it. */
export interface TrainingStage {
  name: string;
  status: "waiting" | "running" | "done" | "FAILED";
  note: string;
  done: number | null;
  total: number | null;
  eta_seconds: number | null;
  extra: string | null;
  took_seconds: number | null;
}

export interface TrainingRun {
  title: string;
  slug?: string;
  started_at?: string;
  updated_at: string;
  elapsed_seconds: number;
  eta_seconds: number | null;
  current: string | null;
  finished: boolean;
  failed: boolean;
  stages: TrainingStage[];
  notes: string[];
}

/**
 * One run's status file, as the server listed it. `active` is the server's
 * own judgement (fresh and unfinished), so the panel does not re-derive it
 * from two other fields.
 */
export interface TrainingEntry {
  slug: string;
  path: string;
  age_seconds: number;
  stale: boolean;
  active: boolean;
  run: TrainingRun;
}

/**
 * A list, because runs coexist — a corpus scan beside a finetune was the case
 * that broke the single shared file. Active runs come first.
 */
export interface TrainingStatus {
  runs: TrainingEntry[];
  dir: string;
}

/**
 * A listening pool, as the dashboard is allowed to see it.
 *
 * COUNTS ONLY, AND THAT IS THE POINT. The server withholds any per-arm result
 * until `reveal_at` trials are answered, because a page you check between doses
 * invites stopping the sitting the moment it looks resolved — optional stopping,
 * which takes a nominal 5% test to 20-30%. So there is deliberately no score to
 * render here, and `can_reveal` is the only hint that one exists yet.
 *
 * `locked_for` is seconds until the next dose may be handed out, counted from
 * the last stored answer rather than from when a dose was served: a reload must
 * not cost half an hour, and the same pool is graded from a phone and a laptop.
 */
export interface ListeningPool {
  id: number;
  name: string;
  question: string;
  dose_size: number;
  trials: number;
  answered: number;
  remaining: number;
  reveal_at: number;
  can_reveal: boolean;
  cooldown_minutes: number | null;
  locked_for: number;
  last_answered_at: string | null;
  closed_at: string | null;
}

/**
 * The corpus browser's shapes, `/api/corpus/*`.
 *
 * `source` is data from the corpus database, not vocabulary this repo
 * defines. Detections are model guesses with timestamps; `candidates` are the
 * model unsure, always counted apart so a table cannot launder them into
 * confident totals.
 */
export interface CorpusSourceRow {
  source: string;
  recordings: number;
  downloaded: number;
  hours: number | null;
  analyzed: number;
  calls: number;
  caw_hours: number;
}

export interface CorpusSpeciesRow {
  species: string;
  calls: number;
  recordings: number;
  caw_minutes: number;
}

export interface CorpusSummary {
  available: boolean;
  path: string;
  sources: CorpusSourceRow[];
  species: CorpusSpeciesRow[];
  totals: {
    recordings: number;
    downloaded: number;
    hours: number | null;
    analyzed: number;
    calls: number;
    candidates: number;
    caw_hours: number;
  } | null;
}

export interface CorpusRecording {
  id: number;
  source: string;
  source_ref: string;
  species: string | null;
  recordist: string | null;
  date: string | null;
  duration_seconds: number | null;
  license: string | null;
  downloaded: number;
  page_url: string | null;
  created_at: string;
  calls: number;
  candidates: number;
  caw_seconds: number;
}

export interface CorpusDetection {
  start_seconds: number;
  end_seconds: number;
  species: string;
  confidence: number | null;
  candidate: number;
  call_type: string | null;
  call_type_confidence: number | null;
}

export interface CorpusRecordingDetail {
  id: number;
  source: string;
  source_ref: string;
  species: string | null;
  recordist: string | null;
  date: string | null;
  duration_seconds: number | null;
  license: string | null;
  downloaded: number;
  page_url: string | null;
  location: string | null;
  lat: number | null;
  lng: number | null;
  quality: string | null;
  playable: boolean;
  detections: CorpusDetection[];
}

export interface CorpusPage {
  recordings: CorpusRecording[];
  total: number;
}

/** One Crow Chat exchange: the request half at enqueue, the reply when the
 *  generation worker finishes. call_type is null for a model that takes no
 *  call types — a bare caw request, not a missing value. */
export interface Generation {
  id: number;
  call_type: string | null;
  model: string;
  seed: number;
  state: "queued" | "running" | "done" | "failed";
  error: string | null;
  created_at: string;
  storage_ref: string | null;
  duration_sec: number | null;
}

/** A model the chat can address, with the call types it takes (possibly none). */
export interface ChatModel {
  name: string;
  call_types: string[];
}

export interface GenerationFeed {
  models: ChatModel[];
  generations: Generation[];
}
