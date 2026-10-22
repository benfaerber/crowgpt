import type { LocationPrecision } from "./location";

/**
 * Everything the recordist can choose, and what survives a restart.
 *
 * Here rather than in AppServices because it is a domain type — the composition
 * root builds the defaults (it needs the device name and the environment), but
 * what a setting *is* has nothing to do with expo.
 */
import type { KnownMic } from "./micPriority";

export interface Settings {
  fieldServerUrl: string;
  enrollToken: string;
  contributorName: string;
  /** What this handset is called — "Pixel 10", "the old one in the glovebox". */
  deviceLabel: string;
  /**
   * Set to join an existing contributor instead of becoming a new one. Only
   * read at enrollment: it is how a second phone reaches the first phone's
   * captures rather than starting a rival corpus.
   */
  claimCode: string;
  /**
   * Which microphone to record through: "builtin", "auto", or "type:<n>".
   *
   * Defaults to the phone's own mic. Android otherwise routes capture to a
   * paired Bluetooth headset, and a corpus recorded through earbuds is a corpus
   * of narrowband speech-processed audio — with nothing on screen to say so.
   */

  /**
   * Microphones in preference order, including ones not currently attached.
   *
   * Supersedes the single `micInput` pin, which is kept so an app updated
   * mid-season starts from whatever was already chosen. The recorder resolves
   * this against what is actually plugged in — see domain/micPriority.
   */
  micPriority: KnownMic[];
  /**
   * Refuse to sync when the server is too old to store what this app records.
   *
   * On by default: a sync that reports success while dropping fields is worse
   * than one that refuses, because the loss is invisible and the phone stops
   * considering those edits pending. Off is for the field, where landing the
   * audio on an old server beats landing nothing.
   */
  strictSync: boolean;
  /** CawScout map view state, remembered because re-flipping four toggles
   *  every visit is exactly the friction that stops a layer being used.
   *  Defaults off: an ordinary capture-review visit wants pins, not dots. */
  mapShowTrees: boolean;
  mapShowScout: boolean;
  mapFamilyHalos: boolean;
  /** Species rows unchecked in the map's checklist, by row label. A list of
   *  what is HIDDEN so newly published species default to visible. */
  mapHiddenSpecies: string[];
  /** Counties unchecked in the map's settings panel, by region slug — the
   *  same hidden-list shape as species, and for the same reason. */
  mapHiddenRegions: string[];
  /** The rail reference lines, from the map's settings panel. */
  mapShowRail: boolean;
  /**
   * Turn captures up for playback.
   *
   * Playback only: the stored WAV is what the analyzer reads and what gets
   * uploaded, and a corpus that has been quietly normalised is one where SNR
   * and absolute level can no longer be measured.
   */
  normalizePlayback: boolean;
  /** How precisely this recordist is willing to say where they were. */
  locationPrecision: LocationPrecision;

  /**
   * Keep recorded coordinates off every screen.
   *
   * Independent of `locationPrecision`, which says whether they are recorded at
   * all. The pair replaced a three-way setting whose middle value was this
   * question wearing the other one's clothes.
   *
   * Defaults to true: a phone whose stored settings predate this field has no
   * answer, and the only safe reading of no answer is "do not show them".
   */
  censorCoords: boolean;
  /**
   * The grid size, in miles, that `fuzzed` precision snaps coordinates to.
   *
   * Kept even while precision is exact or region, so switching to fuzzed and
   * back does not forget the radius someone chose.
   */
  fuzzMiles: number;
  /**
   * Where they are, in their own words — "Utah, US".
   *
   * Asked rather than inferred. Someone who declined GPS is exactly the person
   * an IP lookup must not be used on, and an IP lookup would be wrong anyway:
   * this house's connection claims Idaho.
   */
  homeRegion: string;
  /**
   * Set once the captures recorded before regions existed have been given one
   * from their own GPS fix. A one-off: after it, every capture gets its region
   * when it is recorded.
   */
  regionsBackfilled: boolean;
  /**
   * Keep the microphone open on the capture screen, holding the last
   * {@link PRE_ROLL_SEC} seconds, so pressing Record begins in the past.
   *
   * Off by default, and deliberately a mode rather than a default: a phone in
   * this state is genuinely recording — battery, the privacy indicator, and the
   * mic unavailable to anything else — for as long as the screen is up.
   */
  preRoll: boolean;
  /**
   * Keep listening when the app is not on screen.
   *
   * Split from `preRoll` because the costs are not comparable. Holding the ring
   * while somebody is watching the capture screen is nearly free and needs no
   * permission; holding it from a pocket needs a foreground service, a
   * notification that cannot be dismissed, and the battery to run the
   * microphone all day. One is a convenience, the other is a decision — and a
   * phone that quietly holds its microphone because a *different* switch was
   * flipped is the kind of thing that ends up in an article.
   *
   * Only meaningful with `preRoll` on: there is nothing to keep listening for
   * otherwise.
   */
  backgroundListening: boolean;
  /**
   * Start and stop recording from the headset play/pause button.
   *
   * Off by default, and while off the app holds no MediaSession at all — the
   * button behaves exactly as if this app did not exist. Turning it on is what
   * claims it, which costs every other app the same button: YouTube stops
   * pausing for the whole walk. One switch, one meaning — deliberately not a
   * side effect of pocket listening, which somebody might turn on for its own
   * sake.
   */
  headsetTrigger: boolean;
  /**
   * Start and stop recording from the volume keys, for Bluetooth camera
   * remotes — they enroll as keyboards hardwired to send volume-up, because
   * that is every phone camera's shutter key. Nothing on the remote can be
   * reconfigured, so this claims the key instead.
   *
   * Separate from `headsetTrigger` because the two differ in everything but
   * purpose: this costs no MediaSession and takes nothing from other apps,
   * but only works with the app in front and the screen on — the keys arrive
   * through the Activity. The price is local and stated on the switch: while
   * on, no volume key changes the volume inside the app, the phone's own
   * rocker included.
   */
  volumeShutter: boolean;
  /**
   * Say the recorder's state into the earbuds on a repeating timer — a tick
   * while listening, a double beep while recording, silence when neither.
   *
   * Every silent failure this app has had — the dead capture thread, the
   * reaped process, the button that lost to Spotify — was invisible because
   * mid-session the phone is in a pocket and the state was unknowable without
   * taking it out. Tones rather than words, deliberately: the microphone *is*
   * the field recorder, and anything the phone says out loud lands in the
   * capture — or, while listening, in the pre-roll seconds before the call
   * that made you press Record.
   *
   * Two switches with two cadences because they answer different worries:
   * "is the buffer still alive" is an all-walk question a minute apart, "am I
   * still recording" only matters for the length of a capture and wants
   * answering every few seconds. A state whose switch is off stays silent
   * rather than borrowing the other's sound.
   */
  heartbeatListening: boolean;
  heartbeatRecording: boolean;
  /** Seconds between beats, per state. See domain/heartbeat for the bounds. */
  heartbeatListeningSeconds: number;
  heartbeatRecordingSeconds: number;
  /**
   * Cover the screen while recording, so only a deliberate slide can end it.
   *
   * On by default, which is the opposite of the other modes here — and for the
   * reason that decides the whole design: the costs are not symmetric. A
   * recording that should have stopped and did not wastes some disk. One that
   * stopped when it should not have is gone, and a call does not come back.
   * Every other switch on this screen buys something at a price; this one costs
   * a slide.
   *
   * Written after a stray touch ended a capture mid-greeting. Summer, shorts, a
   * phone in a pocket against a damp leg — a capacitive screen reads that as a
   * finger, and it lands on whatever is under it.
   *
   * Deliberately does not lock the earbud button. That is a physical control
   * being pressed on purpose, not a screen being brushed, and it is how the
   * recordist actually stops a capture with the phone away.
   */
  captureLock: boolean;
  /**
   * Show the idle-mode controls: an armed hour that starts a capture on its
   * own when the crow band gets loud.
   *
   * Nested under `preRoll` like `backgroundListening`, and only meaningful
   * with it: the trigger reads the rolling buffer's own PCM, and the pre-roll
   * ring is what puts the approach on the front of every auto capture.
   * Turning it on turns pocket listening on with it — the armed hour runs
   * with the screen off, and the switch that says so should be visibly on.
   *
   * A visibility switch rather than the arming itself — arming is a deliberate
   * act on the capture screen, per session, because an unattended microphone
   * that starts recordings is not a state to wander into from a settings
   * toggle flipped weeks ago. See domain/idle for every number below.
   */
  idleMode: boolean;
  /** How long an armed session lasts before standing down, in minutes. */
  idleArmMinutes: number;
  /** Silence that ends an auto capture, in seconds. */
  idleHoldSeconds: number;
  /** The longest one auto capture may run, in minutes. */
  idleMaxCaptureMinutes: number;
  /** Auto captures per session before the trigger gives up on the evening. */
  idleMaxCaptures: number;
  /** How far above the measured floor a buffer must sit, in dB. */
  idleTriggerDb: number;
  /** The absolute gate in dBFS, under which nothing triggers. */
  idleMinDb: number;
  /**
   * The last answers given to "They know me as" and "How far away?", carried
   * forward as the pre-selection on the next capture.
   *
   * The value still belongs to the capture — config_store.py makes the case
   * for that and it stands: you can be a stranger in a new territory and a
   * feeder on your own block in the same morning. This is only the observation
   * that the answer is nearly always the same one, and re-choosing a constant
   * is friction on the one screen that should be fast. Empty means nothing
   * remembered yet — or "Not said" chosen last, which must also carry forward.
   */
  lastObserverRole: string;
  lastDistanceBand: string;
}

/**
 * What a fresh capture starts out claiming, from the remembered answers.
 *
 * Undefined rather than empty when nothing is remembered: an empty string on
 * the capture would sync as an answer, and "nobody said" has to stay
 * distinguishable from every real value.
 */
export function stickyCaptureDefaults(
  settings: Settings,
): { observerRole?: string; distanceBand?: string } {
  return {
    observerRole: settings.lastObserverRole || undefined,
    distanceBand: settings.lastDistanceBand || undefined,
  };
}

/**
 * Resolving stored settings against the defaults.
 *
 * Its own function because it is the join between two things that drift: what
 * the app ships with, and what a phone saved months ago. A setting added since
 * the last save has no stored value and must take its default; a setting the
 * recordist chose must survive every launch and every update.
 *
 * Pure, so the answer to "does my microphone choice stick?" is a test rather
 * than a trace through four files.
 */
export function resolveSettings<T extends object>(defaults: T, stored?: Partial<T>): T {
  // JSON.stringify drops undefined, so a stored object never carries an
  // explicit undefined that could clobber a default back to nothing.
  return { ...defaults, ...(stored ?? {}) };
}
