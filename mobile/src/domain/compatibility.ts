/**
 * Whether the server can store what this app sends.
 *
 * The failure this exists for, observed rather than imagined: a v127 phone
 * pushed to a v123 server. The server accepted every request — unknown JSON keys
 * are not an error, they are simply dropped — so `observer_role`, `silent` and
 * the rest vanished, the phone marked those captures delivered, and nothing on
 * either screen said a word. Fieldwork lost with a green tick beside it.
 *
 * Compared on the *wire* version, not the commit count. The first version of
 * this compared commits and would have called a server three tooling commits
 * behind incompatible, when it stored exactly the same fields. A warning that
 * fires on unrelated work is one people learn to click past, and then it is
 * worth less than nothing.
 */

/**
 * The lowest server wire version that can store everything this app sends.
 *
 * Raise it in the same commit that starts sending a new field, and bump
 * `WIRE_VERSION` in fieldserver/build_info.py to match. The two moving together
 * is the whole mechanism.
 *
 *   6  captures.silent_confirmed_at, capture-level context on a silent capture
 *   7  captures.behavior_guess
 *   8  captures.crop_start_sec/crop_end_sec
 *   9  detected_calls.candidate
 *  10  captures.distance_band
 *  11  captures.adult_count/juvenile_count/unaged_count
 *
 *  13  captures.region and the location-precision routes — required, unlike 12:
 *      a server without them accepts a region-only capture and drops the one
 *      field that says where it was, which is the whole point of the setting.
 *
 *  15  labels.config_version — required: a server without the column accepts
 *      the label and drops the one field that says which vocabulary it was
 *      chosen from, which is unrecoverable afterwards and is the entire point.
 *
 *  16  POST /api/captures/<id>/merge — required, and for the sharpest version
 *      of the reason this file exists. A merged capture uploads as an ordinary
 *      recording, so an older server takes it happily; what it drops is the
 *      record that four other captures are the same birds. The corpus is then
 *      holding one event twice with nothing saying so, every count of it is
 *      wrong, and the merge cannot be undone because the offsets went with it.
 *      Green tick, silent loss — exactly the failure at the top of this file.
 *
 *  17  contributors.censor_coords — required, and the least forgiving entry
 *      here. A v16 server accepts the setting and drops the field, so a
 *      recordist who asked for their coordinates to be hidden gets them shown
 *      on the dashboard, having been told the setting saved. Every other
 *      version in this list costs data; this one costs a promise about somebody
 *      home address.
 *
 *  19  crows and labels.crow_id — required. A v18 server accepts a label and
 *      drops the caller, so the app shows the attribution saved while the
 *      corpus never receives it. That is the same silent-loss shape as 17, and
 *      worse in one way: experiment 0017 established the audio does not carry
 *      the caller, so an attribution made while the bird was calling and then
 *      dropped cannot be reconstructed by anyone, ever. Naming a crow is the
 *      one thing in this app that is genuinely unrepeatable.
 *
 * Deliberately not 12. That version added /api/logs, and the app does push to
 * it — but a log line is disposable, and refusing to sync a field recording
 * because the server cannot store the app's diagnostics would be the tail
 * wagging the dog. An older server simply 404s the log push, which LogSync
 * swallows. This number is for what the corpus would silently lose.
 */
// 21 does not move it either, and the reason is the one this file's test names.
// A server too old for dictations has no route at all, so the push 404s: the
// phone keeps the note, logs the refusal, and sends it when the server catches
// up. Nothing is accepted and dropped, which is the failure this number exists
// to catch — an older server simply cannot take a memo yet, the same shape as
// the /api/logs case below.
//
// Still 17, and 20 does not move it either. v20 adds nothing_to_label_at, which
// this app does now send — but a v19 server dropping it costs one recording
// staying in a queue on this phone until it is dismissed again. Nothing is
// observed of a bird in that flag and nothing becomes unrecoverable, which is
// the test this number applies. Refusing to sync a morning's recordings over it
// would be the tail wagging the dog.
//
// 22 moves it, for the reason 19 did. At fuzzed precision the phone snaps
// coordinates to a coarse grid and sends coord_fuzz_miles beside them, saying
// how coarse. A v21 server accepts the snapped coordinates and drops the
// radius, so the corpus stores fixes a few miles wide that are forever
// indistinguishable from exact ones — accepted and silently mislabelled, which
// is precisely what this number exists to catch.
//
// 23 moves it, same asymmetry again. Idle mode sends captures.trigger =
// "auto" on recordings no person started; a v22 server accepts the capture and
// drops the flag, and an unattended recording — role and distance blank on
// purpose, trigger possibly a siren — masquerades forever as a deliberate
// field recording. The whole point of the flag is that this must not happen
// silently.
export const REQUIRED_WIRE_VERSION = 23;

/**
 * The two fields of `/api/health`'s build object this app needs.
 *
 * A narrow view on purpose: the dashboard declares the whole thing (commit,
 * branch, dirty) as `ServerBuild` in `dashboard/src/buildInfo.ts`, and this is
 * a strict subset of it. Keep it that way — the two were disjoint shapes under
 * one name until 2026-07-31, and the missing field was `wire`, on the side that
 * shows an operator whether a sync is about to lose data.
 */
export interface ServerBuild {
  /** Commit count — for display. Not what compatibility turns on. */
  version: number;
  /** What the server can store. Absent on one too old to say. */
  wire?: number;
}

export interface Compatibility {
  /**
   * The server answered at all.
   *
   * Kept apart from `serverBehind` because they call for opposite responses:
   * an old server means "sync anyway and know what you lose", an absent one
   * means "stop now". Conflating them is how a sync in a park spent twenty
   * minutes timing out one capture at a time.
   */
  reachable: boolean;
  /** The server cannot store some of what this app sends. */
  serverBehind: boolean;
  /** One line for the sync bar, or undefined when there is nothing to say. */
  warning?: string;
}

/**
 * A server *ahead* is fine and is the normal state during development — the
 * laptop is always the first thing rebuilt. Only behind loses data.
 *
 * A server that reports no wire version at all predates the field this checks,
 * which makes it definitively older than anything requiring one. That is a real
 * answer rather than an unknown, so it warns.
 */
export function compatibility(server: ServerBuild | undefined): Compatibility {
  if (!server) return { reachable: true, serverBehind: false }; // nothing to claim
  const wire = server.wire ?? 0;
  if (wire >= REQUIRED_WIRE_VERSION) return { reachable: true, serverBehind: false };
  return {
    reachable: true,
    serverBehind: true,
    warning:
      `Server is too old to store everything this app records ` +
      `(it speaks v${wire}, this app needs v${REQUIRED_WIRE_VERSION}). ` +
      `Restart the field server.`,
  };
}
