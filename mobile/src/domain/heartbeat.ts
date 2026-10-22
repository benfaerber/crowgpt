/**
 * The heartbeat cue's numbers, and the join between the settings text box and
 * an interval the recorder can actually run.
 */

/**
 * Different defaults because the two heartbeats answer different worries.
 * "Is the buffer still alive" is an all-walk question — a minute apart keeps
 * an hour of pocket listening at sixty ticks rather than 360. "Am I still
 * recording" only matters for the length of a capture, and ten seconds is the
 * most silence anyone wants between reassurances mid-take.
 */
export const HEARTBEAT_LISTENING_DEFAULT_SEC = 60;
export const HEARTBEAT_RECORDING_DEFAULT_SEC = 10;

/**
 * The floor exists because the tone itself takes ~0.4 s and music dips around
 * each one — below this the cue stops being a heartbeat and becomes a siren.
 * The ceiling keeps a typo ("100" meant, "1000" typed) from producing a cue
 * that fires less than once a field session, which reads as broken.
 */
export const HEARTBEAT_MIN_SEC = 5;
export const HEARTBEAT_MAX_SEC = 600;

/**
 * What the text box means, as seconds.
 *
 * Clamps rather than rejects: someone typing "3" wanted a fast heartbeat and
 * gets the fastest one offered, which is closer to their intent than their old
 * value reappearing. Non-numbers fall back to what was already set — a box
 * blurred mid-edit must not move the setting.
 */
export function normalizeHeartbeatSeconds(text: string, fallback: number): number {
  const parsed = Number.parseInt(text.trim(), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(HEARTBEAT_MAX_SEC, Math.max(HEARTBEAT_MIN_SEC, parsed));
}
