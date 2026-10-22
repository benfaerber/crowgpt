import type { AudioInputDescription } from "../recording/Recorder";

/**
 * Which microphone to record through, as an ordered preference rather than a
 * single pin.
 *
 * The case this exists for: you buy a good microphone, set it as first choice,
 * and one morning walk out without it. A single pinned input either falls back
 * silently to something you did not choose, or fails. A list says what should
 * happen instead — second choice, then third, then the phone's own — and the
 * capture records which one it actually got.
 *
 * Every microphone ever seen is remembered, because the interesting ones are
 * absent most of the time. A list you can only arrange while the hardware is
 * plugged in is one you cannot arrange on the walk out of the door.
 *
 * Matching is by *type*, not by device id: ids are assigned per connection, so
 * a preference stored by id stops matching the moment the mic is unplugged and
 * plugged back in. The consequence is that two microphones of the same type —
 * two USB mics — are indistinguishable here. One is the normal case; if that
 * ever changes, this is where it changes.
 */
export interface KnownMic {
  /** What to pass to the recorder: "builtin", "auto", or "type:<n>". */
  preference: string;
  /** What it called itself when last seen, for the list. */
  label: string;
  /** e.g. "USB_HEADSET". Kept so a renamed device is still recognisable. */
  typeLabel?: string;
  /** ISO timestamp of the last time it was attached. */
  lastSeen?: string;
}

/**
 * How enumeration spells the phone's own microphone — `AudioDeviceInfo.TYPE_BUILTIN_MIC`.
 *
 * The settings list spells it {@link BUILTIN}, and both names mean one device.
 * That is survivable while nothing compares them and fatal the moment something
 * does: the buffer-adoption check read a route of `type:15`, compared it to a
 * preference of `builtin`, concluded the microphone had changed and reopened
 * the session — on every input event, for ever, discarding the pre-roll ring
 * each time.
 */
const BUILTIN_TYPE = "type:15";

/**
 * One spelling per device, so two names for the phone mic cannot read as two
 * microphones. Apply to anything crossing between enumeration and the
 * preference list before comparing it.
 */
export function canonicalPreference(preference: string): string {
  return preference === BUILTIN_TYPE ? BUILTIN.preference : preference;
}

/** The phone's own microphone, which is always present and always last. */
export const BUILTIN: KnownMic = {
  preference: "builtin",
  label: "Phone microphone",
  typeLabel: "BUILTIN_MIC",
};

/** How "auto" reads in the list, when somebody has asked for it. */
export const AUTO: KnownMic = {
  preference: "auto",
  label: "Whatever Android picks",
};

/**
 * Turn the old single pin into a starting list.
 *
 * Only for the first launch after the update, and only so the list opens
 * describing what the phone has already been doing. Every entry is named after
 * the hardware — a row reading "Current choice" tells you nothing about *which*
 * microphone, which is the one thing it is there to say.
 *
 * "builtin" seeds nothing, because rememberMics adds the phone's own microphone
 * to every list anyway.
 */
export function seedFromPin(
  pin: string,
  attached: readonly AudioInputDescription[],
): KnownMic[] {
  if (pin === BUILTIN.preference) return [];
  if (pin === AUTO.preference) return [{ ...AUTO }];
  const found = attached.find((input) => input.preference === pin);
  return [{
    preference: pin,
    label: found?.name || found?.typeLabel || "Previously chosen microphone",
    typeLabel: found?.typeLabel,
  }];
}

/**
 * Fold what is attached now into what has been seen before.
 *
 * New microphones are appended rather than promoted: arriving at the top would
 * silently change what the next recording runs through, which is the behaviour
 * this whole feature exists to remove. Plugging something in never reorders
 * anything on its own.
 *
 * The built-in mic is always present, and always last unless deliberately
 * moved — it is the floor, not a choice.
 */
export function rememberMics(
  known: readonly KnownMic[],
  attached: readonly AudioInputDescription[],
  now: string,
): KnownMic[] {
  const merged = known
    .filter((mic) => !NOT_MICROPHONES.has(mic.preference))
    .map(canonicalise);
  const find = (preference: string) => merged.find((m) => m.preference === preference);

  if (!find(BUILTIN.preference)) merged.push({ ...BUILTIN });

  for (const input of attached) {
    if (!input.isExternal) continue;
    const existing = find(input.preference);
    if (existing) {
      // Adopt the current name: a device that reports itself differently after
      // a firmware update is the same microphone, and should not appear twice.
      existing.label = input.name || existing.label;
      existing.typeLabel = input.typeLabel || existing.typeLabel;
      existing.lastSeen = now;
    } else {
      merged.push({
        preference: input.preference,
        label: input.name || input.typeLabel,
        typeLabel: input.typeLabel,
        lastSeen: now,
      });
    }
  }
  return merged;
}

/**
 * Correct the names this app owns, every time the list is read.
 *
 * "builtin" and "auto" are behaviours, not hardware — their labels are ours to
 * define, so a stored one is never authoritative. Written because a placeholder
 * shipped once and then could not be dislodged: it had been saved to settings,
 * so the seeding path that produced it never ran again, and reinstalling the
 * app changed nothing because the settings survived the reinstall.
 *
 * Self-healing beats a migration here. A stored label is a cache of something
 * this file already knows, and a cache that cannot be refreshed is a bug
 * waiting for a release.
 */
/**
 * Entries that should never have been offered.
 *
 * A Pixel enumerates REMOTE_SUBMIX (virtual routing) and ECHO_REFERENCE (the
 * signal the phone is playing) among its inputs. Both were listed as
 * microphones before the native side filtered them, and a phone that saw them
 * once has them saved — so they are dropped on read too. Recording through the
 * second captures the phone's own playback.
 */
const NOT_MICROPHONES = new Set(["type:25", "type:28"]);

function canonicalise(mic: KnownMic): KnownMic {
  if (mic.preference === BUILTIN.preference) return { ...mic, ...BUILTIN };
  if (mic.preference === AUTO.preference) return { ...mic, ...AUTO };
  return { ...mic };
}

/**
 * The highest-ranked microphone that is actually here.
 *
 * Falls through the list in order and ends at the built-in, which is always
 * attached. Returns "builtin" for an empty list rather than "auto": auto is
 * what routes a capture through earbuds, and it should only ever happen because
 * somebody asked for it.
 */
export function resolveMic(
  priority: readonly KnownMic[],
  attached: readonly AudioInputDescription[],
): string {
  const here = new Set(attached.map((input) => input.preference));
  for (const mic of priority) {
    // "auto" and "builtin" name behaviours rather than hardware, so they are
    // always available — reaching either ends the search.
    if (mic.preference === "builtin" || mic.preference === "auto") return mic.preference;
    if (here.has(mic.preference)) return mic.preference;
  }
  return BUILTIN.preference;
}

/**
 * Whether the choice about to be used is the one at the top of the list.
 *
 * False means a fall-through happened — the first choice is not here. Worth
 * saying on the record screen *before* the recording, because afterwards it is
 * only visible in the capture's metadata, which nobody reads at the time.
 */
export function usingFirstChoice(
  priority: readonly KnownMic[],
  attached: readonly AudioInputDescription[],
): boolean {
  if (priority.length === 0) return true;
  return resolveMic(priority, attached) === priority[0].preference;
}

/** Move an entry up or down, for the arrows in Settings. */
export function reorder(mics: readonly KnownMic[], from: number, to: number): KnownMic[] {
  if (from === to || from < 0 || to < 0 || from >= mics.length || to >= mics.length) {
    return [...mics];
  }
  const next = [...mics];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}
