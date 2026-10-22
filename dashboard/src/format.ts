/**
 * Display helpers.
 *
 * Copied from the field app rather than shared through a package — a build
 * step and a versioning story would cost more than fifty lines of overlap
 * does. But "if the two ever drift nothing breaks" turned out to be wrong in
 * one specific way: formatDuration drifted to a different *unit*, so code
 * moved between the apps compiled fine and showed durations a thousand times
 * off. The rule now: formatBytes, formatDuration and describeOffset are
 * verbatim copies of mobile/src/ui/theme.ts and domain/sightings.ts — same
 * unit (milliseconds), same output — and the seconds→ms conversion happens
 * visibly at the call site.
 */

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "—";
  return when.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatCoords(
  latitude: number | null | undefined,
  longitude: number | null | undefined,
  places = 4,
): string {
  if (latitude == null || longitude == null) return "—";
  return `${latitude.toFixed(places)}, ${longitude.toFixed(places)}`;
}

export function formatConfidence(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

/**
 * The microphone a recording came through.
 *
 * Anything that isn't the built-in mic is worth calling out: a Bluetooth headset
 * records narrowband with speech processing applied, so the clip is worth much
 * less as training data and nothing in the audio itself admits it.
 */
export function describeMic(
  device: string | null,
  honoured: number | null,
): { text: string; suspect: boolean } | null {
  if (!device) return null;
  return {
    text: device + (honoured === 0 ? " (pin refused)" : ""),
    suspect: device !== "BUILTIN_MIC",
  };
}

/**
 * "5m after", "1m 30s before" — how far an out-of-frame sighting sits from the
 * recording it relates to. Signed: negative is before it.
 *
 * Duplicated from the field app for the reason at the top of this file.
 */
export function describeOffset(offsetSec: number): string {
  if (offsetSec === 0) return "as it ended";
  const magnitude = Math.abs(offsetSec);
  const minutes = Math.floor(magnitude / 60);
  const seconds = Math.round(magnitude % 60);
  const span =
    minutes > 0
      ? seconds > 0
        ? `${minutes}m ${seconds}s`
        : `${minutes}m`
      : `${seconds}s`;
  return `${span} ${offsetSec > 0 ? "after" : "before"}`;
}

/**
 * Whether this browser is currently masking precise locations.
 *
 * Kept here rather than in a query because it is a property of the screen
 * somebody is about to photograph, not of the fleet. It survives a reload,
 * because the moment it does not is the moment a screenshot goes out with
 * somebody's street on it.
 */
const PRESENTATION_KEY = "cawtalker.presentation";

export function presentationMode(): boolean {
  try {
    return localStorage.getItem(PRESENTATION_KEY) === "1";
  } catch {
    return false;
  }
}

export function setPresentationMode(on: boolean): void {
  try {
    localStorage.setItem(PRESENTATION_KEY, on ? "1" : "0");
  } catch {
    /* storage blocked; the toggle still works for this session */
  }
}

/**
 * What to print for a place, honouring both the contributor's choice and the
 * screenshot the operator is about to take.
 *
 * One function, used everywhere a location appears. Masking decided per panel
 * is how three of them honour the setting and the fourth quietly does not.
 *
 * NOT the same function as the phone's `describePlace`
 * (`mobile/src/domain/location.ts`), which is why this one is named for the
 * operator. Both decide whether coordinates may be shown and they agree on the
 * policy today, but they read it from different places — the phone takes
 * precision from its own settings, this takes it off the row the server sent —
 * and this one adds presentation masking, which has no phone equivalent. They
 * shared a name until 2026-07-31, on privacy code, where a call site moved
 * between the two apps would have compiled into a different masking decision.
 *
 * **Change one, look at the other.** There is no shared module to make that
 * automatic; FUTURE.txt lists every such pair, and why extracting one was
 * decided against.
 */
export function describePlaceForOperator(
  row: {
    latitude?: number | null;
    longitude?: number | null;
    region?: string | null;
    location_precision?: string | null;
    censor_coords?: number | boolean | null;
  },
  masking = presentationMode(),
): string {
  const theirs = row.location_precision ?? "exact";
  // Two independent questions since wire 17. `location_precision` says whether
  // coordinates were recorded; `censor_coords` says whether they may be shown.
  // Either one withholding is enough, and they are checked separately because
  // the migration folded the old `exact_private` into exact + censor — a row
  // that used to be masked by its precision is now masked by its flag, and
  // reading only the precision would publish it.
  const censored = Boolean(row.censor_coords);
  // `exact_private` should no longer exist in the database, but a row that
  // escaped the backfill must keep its promise rather than be revealed by it.
  if (censored || masking) return row.region ?? "—";
  // Fuzzed rows hold coordinates already snapped to a miles-wide grid — safe
  // to show, but marked and shortened so they never read as an exact fix.
  if (theirs === "fuzzed") {
    if (row.latitude == null || row.longitude == null) return row.region ?? "—";
    return `≈ ${formatCoords(row.latitude, row.longitude, 2)}`;
  }
  if (theirs !== "exact") return row.region ?? "—";
  return formatCoords(row.latitude, row.longitude);
}
