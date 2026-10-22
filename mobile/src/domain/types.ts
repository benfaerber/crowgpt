import { hasUnsyncedEdits } from "./revision";

/**
 * The local-first domain model.
 *
 * The phone is the source of truth until a sync is asked for: a capture is
 * written to the local store the moment recording stops and lives there
 * complete, whether or not the field server has ever heard of it. Every field
 * the server needs is therefore stored locally too — syncing is a projection of
 * this record onto the API, never the other way round.
 */

/** Where a capture is in its journey to the field server. */
export type SyncState =
  /** Recorded and stored locally. Nothing has been sent. */
  | "local"
  /** A sync is in flight for this capture right now. */
  | "syncing"
  /** Fully uploaded and acknowledged by the server. */
  | "synced"
  /** A sync attempt failed; `lastError` says why. Retryable. */
  | "failed";

export interface CaptureRecord {
  /**
   * The device's own id, generated at record time and never reused. Sent to the
   * server as `client_uuid`, which makes create idempotent: a retry after a lost
   * response returns the original row instead of duplicating it.
   */
  uuid: string;
  /** Same idea for the capture's audio file — its own stable id. */
  mediaUuid: string;

  /**
   * What the recordist calls this capture — "Edgar on the wire", "the mobbing".
   *
   * Optional, and never auto-filled: a name invented by the app would be a
   * label nobody chose, and the list would look named while still being
   * unsearchable. Falls back to the timestamp, which is how a machine tells two
   * recordings apart rather than how a person does.
   */
  name?: string;

  recordedAt: string;
  durationMs: number;
  sampleRate: number;
  channels: number;

  /** Absolute path to the WAV on the device. */
  audioPath: string;
  /** Size of that file in bytes. */
  bytes: number;

  /**
   * Optional video shot alongside the audio, for context.
   *
   * The camera records **muted** and `raw-audio` captures the sound separately,
   * so the WAV above stays the pristine 48 kHz signal the model is trained on.
   * A camera's own track is compressed and speech-processed — usable to watch,
   * not to learn from — so the two are deliberately kept as separate files
   * rather than one muxed mp4.
   */
  videoPath?: string;
  videoBytes?: number;
  /** Its own idempotency key, since it is a second media row server-side. */
  videoMediaUuid?: string;
  videoServerMediaId?: number;
  videoUploadedBytes?: number;

  /**
   * Which microphone the OS actually routed this capture to, e.g. "BUILTIN_MIC".
   *
   * Recorded per capture rather than inferred from the current setting: the
   * setting says what was asked for, and the whole failure mode here is a
   * request that was quietly not honoured. A recording made through a Bluetooth
   * headset is narrowband and speech-processed, which matters enormously to what
   * it is worth training on — so it has to be knowable afterwards, not guessed.
   */
  inputDevice?: string;
  /** False when a pinned microphone was refused and something else was used. */
  inputHonoured?: boolean;
  /**
   * Seconds at the head of this recording that were captured before the button
   * was pressed, from the rolling buffer. Absent or 0 when it wasn't running.
   *
   * Worth keeping per capture: it says where in the file the human reaction is,
   * which is roughly where the call is. A labeller scrubbing a pre-rolled clip
   * is looking near this mark, not at the start.
   */
  preRollSec?: number;
  /**
   * The app build that made this recording, as a commit count.
   *
   * Stamped when the button is pressed, not when the capture syncs: those can
   * be days and several releases apart, and the device row only ever holds the
   * *latest* version a phone reported. Without this, "which build recorded
   * capture 69" has no answer at all — and it is the question you ask first
   * when one batch of audio looks different from the rest.
   */
  appVersion?: number;
  appCommit?: string;

  /**
   * "auto" when the idle trigger started this recording rather than a
   * person. Undefined means a deliberate press, and stays undefined rather
   * than "manual" — the null-means-nobody-said convention, and every capture
   * before this field existed was manual by construction.
   *
   * The corpus discipline is knowing what is real, and an unattended capture
   * is a different kind of real: nobody witnessed it, its role and distance
   * are unfilled on purpose, and a trigger can be fooled by a siren. This is
   * what keeps those rows from masquerading as deliberate field recordings.
   */
  trigger?: "auto";

  /**
   * What the recordist was to these crows when this was recorded — a key from
   * the served `observer_roles` vocabulary.
   *
   * The variable that flips the meaning of everything else on the tape: a crow
   * that knows you feeds it behaves nothing like one meeting you, same bird and
   * same street. Undefined means nobody said, which is emphatically not the
   * same as "stranger".
   */
  observerRole?: string;

  /**
   * Roughly how far away the bird was — a key from DISTANCE_BANDS.
   *
   * The one variable that confounds every comparison between recordists and
   * between sites. A hooded crow in Berlin that tolerates a two-metre approach
   * and an American Crow thirty metres up a rooftop produce audio differing in
   * signal-to-noise and spectral tilt before either bird has said anything
   * different.
   *
   * Nothing in a WAV says how far away the bird was and no analysis recovers
   * it, so it is recorded here or it is lost. Undefined means nobody said.
   */
  distanceBand?: string;

  /**
   * Who was there: adults, juveniles, and birds whose age you couldn't tell.
   *
   * Three counters rather than two because the descriptions demanded it — "3
   * crows on 1 branch" states a number and no ages, and a schema of adults and
   * juveniles could only hold that by inventing one.
   *
   * Undefined means nobody counted, which must stay distinguishable from zero:
   * zero adults is a real observation about a group of fledglings. Age is only
   * judgeable close up, so distanceBand is what says whether a split is
   * credible.
   */
  adultCount?: number;
  juvenileCount?: number;
  unagedCount?: number;

  /**
   * When a human listened to the whole recording and heard no crow calls.
   *
   * Undefined means nobody has checked — emphatically not the same claim, and
   * the distinction is the entire point. An unreviewed capture and a
   * listened-to-and-genuinely-quiet one are identical from outside unless this
   * is written down.
   *
   * This is the denominator. The corpus can already say what was happening when
   * a crow called; without confirmed-silent recordings it can never say how
   * often the same thing happened and the crow said nothing.
   */
  silentConfirmedAt?: string;

  /**
   * When somebody said this recording has nothing worth labelling.
   *
   * Not the same claim as {@link silentConfirmedAt}, and the difference is why
   * this exists at all. That one says a human listened to the whole thing and
   * heard no crow calls — a real observation about the audio, and the
   * denominator every "how often do they call at X" question needs. This one
   * says the recording is not field material: a test upload, a seeded clip, a
   * walk that caught nothing but traffic. One is about crows; the other is
   * about the file.
   *
   * Its job is to let the label queue empty. A queue that lists recordings
   * nobody will ever label is ignored within a week, and then it is worse than
   * no queue — it has taught the one person who uses it to look past it.
   *
   * Undefined means nobody has said either way, which is what "waiting" means.
   * Set it by mistake and labelling the capture anyway overrides it, because a
   * label is evidence and this is only an intention.
   */
  nothingToLabelAt?: string;

  /**
   * What the recordist thinks was going on — "I guess they caw at a group of
   * teenagers".
   *
   * Kept apart from labels, context and the description on purpose. Those
   * record what a human *witnessed*; this records what they *concluded*, and a
   * corpus that cannot tell the two apart is one where every finding is already
   * assumed somewhere in the data.
   *
   * Never exported for training, never entered into the calls × context matrix.
   * Its value is the opposite: the guesses that keep recurring across a season
   * are the hypotheses worth designing a real test for.
   */
  behaviorGuess?: string;

  /**
   * The captures this one was joined from, in play order.
   *
   * Set on the merged capture only. Its audio is assembled from these on read
   * rather than written to disk, so this is not decoration — without it the
   * capture has no audio at all.
   */
  mergedFrom?: string[];

  /**
   * The merged capture this one was folded into.
   *
   * Set on the parts. They keep their row and their audio and stop being
   * listed, which is what makes a merge reversible: nothing was destroyed, so
   * clearing this field brings them back.
   */
  mergedInto?: string;

  /**
   * Peak envelope computed on the phone, so a capture has a waveform before it
   * has ever been uploaded — and something to crop against. JSON array of 0..1.
   */
  envelopeJson?: string;

  /**
   * Crop, in seconds from the start of the recording. Only the selected span is
   * uploaded; the file on disk is never modified, so a crop is always undoable
   * and a mis-set handle can't destroy a recording.
   */
  cropStartSec?: number;
  cropEndSec?: number;

  /**
   * Marks a capture worth keeping — a real observation rather than test data.
   * Seeded captures are created with this off, and the seeder refuses to clear
   * anything with it on, so a reseed cannot take a field recording with it.
   */
  keep?: boolean;

  /** Local uuid of the family this capture belongs to. Optional by design. */
  familyUuid?: string;

  latitude?: number;
  longitude?: number;
  locationName?: string;
  /**
   * "Utah, US". Resolved from the fix when there is one and from the
   * recordist's own answer when there is not — never from an IP address, which
   * names the ISP's registration rather than the person. See domain/location.ts.
   */
  region?: string;
  notes?: string;

  /**
   * What the recordist says happened — the context half of the ground truth,
   * written in prose rather than picked from a vocabulary. Stored on the capture
   * because there is one per capture today; it reaches the server as a proper
   * observation, which is a list, so this can grow into one later.
   */
  description?: string;
  /** Stable id for the description, so a retried push edits rather than duplicates. */
  descriptionUuid?: string;
  descriptionUpdatedAt?: string;
  /** When the server last accepted it — shown to the user, never used to decide. */
  descriptionSyncedAt?: string;
  /**
   * The exact text the server last accepted. Whether a push is owed is decided
   * by comparing against this rather than by comparing timestamps: a field
   * phone's clock can be wrong or skewed, and a wrong clock must not be able to
   * strand a description or re-send it forever.
   */
  descriptionSyncedBody?: string;

  syncState: SyncState;
  /** Ids the server assigned, remembered so a resumed sync skips work already done. */
  serverCaptureId?: number;
  serverMediaId?: number;
  /** How many bytes the server has confirmed receiving — where a resume starts. */
  uploadedBytes: number;
  syncedAt?: string;
  attempts: number;
  lastError?: string;

  /**
   * Bumped whenever an edit changes something the server holds (see
   * `domain/revision.ts`). Local ahead of synced means the capture owes a push,
   * which is what lets a description typed *after* the upload still arrive.
   */
  localRevision?: number;
  syncedRevision?: number;
}

/** A capture the user has recorded but not yet described — everything except sync bookkeeping. */
export type NewCapture = Omit<
  CaptureRecord,
  "syncState" | "uploadedBytes" | "attempts" | "serverCaptureId" | "serverMediaId" | "syncedAt" | "lastError"
>;

export function isPendingSync(capture: CaptureRecord): boolean {
  if (capture.syncState === "syncing") return false;
  // A part of a merge is never pushed on its own. The merged capture carries
  // every part's samples, so a part that never reached the server travels
  // inside the joined audio and loses nothing by not being sent, and one that
  // synced before the merge is already up there with the merge record to say
  // what replaced it. Either way, sending it now would upload the same audio
  // a second time for no gain.
  if (capture.mergedInto !== undefined) return false;
  return (
    capture.syncState === "local" ||
    capture.syncState === "failed" ||
    hasUnsyncedEdits(capture)
  );
}
