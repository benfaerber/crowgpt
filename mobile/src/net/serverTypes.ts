import type { ContributorRole, Identity } from "../domain/identity";

/**
 * The server's side of the wire, as the phone reads it.
 *
 * Shapes only — every field spelled the way the JSON arrives (snake_case),
 * because these are transcriptions of `fieldserver/api.rest`, not domain
 * types. The client class in FieldServerClient.ts speaks them; everything
 * else should import the shape it needs from here rather than pulling in
 * the HTTP client to get a type.
 */

export interface EnrolledDevice {
  deviceToken: string;
  identity: Identity;
}

export interface ServerContributor {
  id: number;
  public_uuid: string;
  display_name: string;
  role: ContributorRole;
  status: "active" | "suspended";
}

export interface ServerDevice {
  id: number;
  label: string | null;
  platform: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
}

export interface ServerCapture {
  id: number;
  client_uuid: string | null;
  status: string;
  /**
   * Everything below is present on a full read, and used by restore.
   *
   * This list has to stay level with what the phone SENDS in SyncEngine, or a
   * restore quietly hands back less than it was given: a field missing here is
   * not a type error, because every one of them is optional, so it simply never
   * reaches the rebuilt record. Two exceptions are deliberate rather than
   * missing — see the note in Restore.restoreOne.
   */
  name?: string | null;
  keep?: number | null;
  recorded_at?: string | null;
  duration_sec?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  location_name?: string | null;
  region?: string | null;
  notes?: string | null;
  observer_role?: string | null;
  behavior_guess?: string | null;
  silent_confirmed_at?: string | null;
  nothing_to_label_at?: string | null;
  distance_band?: string | null;
  adult_count?: number | null;
  juvenile_count?: number | null;
  unaged_count?: number | null;
  app_version?: number | null;
  app_commit?: string | null;
  /** "auto" when the idle trigger made the recording. */
  trigger?: string | null;
}

export interface ServerMedia {
  id: number;
  client_uuid: string | null;
  kind?: string;
  format?: string;
  sample_rate?: number;
  channels?: number;
  /** Bytes the server already holds — the offset a resumed upload continues from. */
  bytes: number;
  upload_state: "pending" | "partial" | "complete";
}

/** A dictation slot as the server describes it. `bytes` is the resume offset. */
export interface ServerDictation {
  id: number;
  client_uuid?: string | null;
  format?: string;
  bytes: number;
  upload_state: "pending" | "partial" | "complete";
  transcript?: string | null;
}

export interface AnalysisJob {
  id: number;
  state: "queued" | "running" | "done" | "failed";
  error?: string | null;
}

export interface AnalysisResult {
  capture_id: number;
  duration?: number;
  waveform?: number[];
  model_version?: string;
  calls: DetectedCall[];
}

export interface DetectedCall {
  start_sec: number;
  end_sec: number;
  species: string;
  scientific_name?: string;
  call_type?: string | null;
  confidence?: number | null;
  crow_conf?: number | null;
  /**
   * Other call types the head also heard in this span.
   *
   * A region can hold more than one call. Capture 104 is an 18-second
   * "begging" region with an adult cawing over the fledgling at 12s, and until
   * the head became one-vs-rest the analyzer took argmax and dropped the rest —
   * so the second call was neither reported nor labellable, and the corpus held
   * zero overlapping labels while the field held plenty.
   *
   * Absent on captures analysed before that, which is why it is optional
   * rather than defaulted: "the head heard nothing else" and "the head could
   * not have told you" are different, and only one of them is news.
   */
  alternates?: { call_type: string; confidence: number }[];
  /**
   * Whether those alternates are independent probabilities or a runner-up.
   *
   * One-vs-rest classes do not compete, so a second high score means it heard
   * two things. A softmax's do, so the same number means it was torn between
   * two readings of one. Only the American Crow head has been retrained, so
   * both kinds are live and the claim travels with the numbers.
   */
  multi_label?: boolean;
  /**
   * 1 when the model named a corvid but was not confident.
   *
   * Offered for labelling and counted as nothing until a human rules. The gate
   * that used to discard these closed a loop — the analyzer proposes, the
   * recordist confirms, confirmations become training data, so the corpus could
   * only hold calls the model already scored well.
   */
  candidate?: number | null;
}

