import type { ActiveSessionInput, AudioInputDescription } from "../recording/Recorder";
import {
  AUTO,
  BUILTIN,
  canonicalPreference,
  resolveMic,
  usingFirstChoice,
  type KnownMic,
} from "./micPriority";

/**
 * Which microphone the app is on, answered once for every screen that asks.
 *
 * There used to be three answers. The settings picker resolved the preference
 * list against what was plugged in; the capture screen resolved it again, its
 * own way, for the caption and the warning; and the recorder pinned a device in
 * native code and told nobody until the recording stopped. Three derivations of
 * one fact, and the moment they disagreed the two that were only *predictions*
 * both looked confident.
 *
 * That is how capture 107 happened. The Rode was plugged in after the rolling
 * buffer had already opened on the phone mic. Every prediction switched to the
 * Rode — the caption named it, and the warning went from yellow back to plain
 * white, which is the app saying "nothing is wrong here". The one thing that
 * had not changed was the open session, and it was the only one that mattered.
 *
 * So: the open session wins whenever there is one. The list is a statement
 * about the *next* recording, and this says so rather than blurring the two.
 */
export interface MicState {
  /** The preference being described — the session's, when one is open. */
  preference: string;
  /** What to call it on screen. */
  label: string;
  /**
   * True when this describes a microphone that is actually open, false when it
   * is a prediction about what the next recording would use. A caption that
   * cannot tell you which of those it is saying is the bug this type exists to
   * remove.
   */
  live: boolean;
  /** What the recordist needs told, if anything. Rendered in warning colour. */
  warning?: string;
}

/**
 * Whether the open session should be torn down and reopened on `wanted`.
 *
 * A session pins its microphone when it opens and cannot be re-pointed, so
 * adopting one plugged in afterwards means a new session — and that costs the
 * pre-roll ring. Worth it: plugging a microphone in is an explicit act that is
 * nearly always followed by wanting to record through it, and an empty ring is
 * visible on the button while a capture through the wrong microphone is visible
 * to nobody until it is played back.
 *
 * Pure, and separate from the hook that acts on it, because every clause here is
 * a rule somebody will want to check without a phone in their hand.
 */
export function shouldReopenSession(
  session: ActiveSessionInput | null,
  wanted: string,
): boolean {
  // Nothing open: the next session will pick `wanted` on its own.
  if (!session) return false;
  // Never mid-capture. Reopening ends the recording and discards what is
  // already on disk, which is worse than the wrong microphone — and unlike the
  // buffer, the recordist asked for this one explicitly.
  if (session.recording) return false;
  // The policy has not chosen a route yet, so there is nothing to disagree
  // with. Acting now would reopen against a guess.
  if (session.routed === null) return false;
  // Canonicalised, because the route comes from enumeration and `wanted` from
  // the preference list, and those spell the phone's own microphone
  // differently. Comparing them raw made every input event look like a device
  // change and reopened the session on a loop.
  return canonicalPreference(session.routed) !== canonicalPreference(wanted);
}

function labelFor(
  preference: string,
  priority: readonly KnownMic[],
  attached: readonly AudioInputDescription[],
): string {
  if (preference === AUTO.preference) return AUTO.label;
  if (preference === BUILTIN.preference) return BUILTIN.label;
  return (
    priority.find((mic) => mic.preference === preference)?.label
    ?? attached.find((input) => input.preference === preference)?.name
    ?? preference
  );
}

export function micState({
  priority,
  attached,
  session,
}: {
  priority: readonly KnownMic[];
  attached: readonly AudioInputDescription[];
  /** The open microphone session, or null when nothing is open. */
  session: ActiveSessionInput | null;
}): MicState {
  const wanted = resolveMic(priority, attached);
  const wantedLabel = labelFor(wanted, priority, attached);
  const fellThrough =
    priority.length > 0 && !usingFirstChoice(priority, attached)
      ? `${priority[0].label} isn't connected — recording on ${wantedLabel}`
      : undefined;

  if (!session) {
    return { preference: wanted, label: wantedLabel, live: false, warning: fellThrough };
  }

  // `routed` is null for the moment between opening the session and the policy
  // choosing a route. Falling back to the request is the best available answer,
  // but it is not evidence of a mismatch — so the comparison below is skipped
  // until there is something real to compare.
  const actual = canonicalPreference(session.routed ?? session.requested);
  const actualLabel = labelFor(actual, priority, attached);

  let warning = fellThrough;
  if (session.routed !== null && actual !== canonicalPreference(wanted)) {
    // The two really have parted company, which a running session cannot fix:
    // the device is pinned once, when the session opens.
    warning =
      `Recording on ${actualLabel}. The list now says ${wantedLabel} — a session `
      + "cannot change microphone once it is open.";
  } else if (session.honoured === false) {
    warning = `Asked for ${labelFor(session.requested, priority, attached)} and the phone gave ${actualLabel}.`;
  }

  return { preference: actual, label: actualLabel, live: true, warning };
}
