/**
 * How precisely a recordist is willing to say where they were.
 *
 * A crow corpus is a map of where one person walks. Forty captures with GPS
 * fixes describe a home, a commute and a routine, and that is true of every
 * contributor who joins — the German one, and the dozen in Salt Lake who have
 * not signed up yet. Coordinates are also genuinely needed: BirdNET's species
 * filter takes lat/lon, and "does this call differ by territory" cannot be
 * asked without them.
 *
 * So it is a choice, made per contributor, and it is enforced where it can
 * actually be enforced — on the phone, before anything is sent. A privacy
 * setting the server applies is a promise; one the phone applies is a fact.
 */
export type LocationPrecision =
  /** Coordinates recorded and stored. Whether they are *shown* is censorCoords. */
  | "exact"
  /**
   * Coordinates recorded, but snapped to a grid a few miles wide before
   * anything leaves the phone. The territory question survives at this
   * resolution — which side of the valley, which park — while the answer to
   * "which house" never exists off this handset.
   */
  | "fuzzed"
  /**
   * No coordinates at all. Nothing to leak, nothing to reveal by accident,
   * and the region is still enough to say which population was recorded.
   */
  | "region";

export const PRECISIONS: readonly {
  key: LocationPrecision;
  label: string;
  detail: string;
}[] = [
  {
    key: "exact",
    label: "Record coordinates",
    detail:
      "Coordinates on every capture. Best for the science — territory and " +
      "species filtering both need them. Use \u201ccensor coordinates\u201d to keep " +
      "them out of what is displayed.",
  },
  {
    key: "fuzzed",
    label: "Within a few miles",
    detail:
      "Coordinates are snapped to a coarse grid before they leave this phone. " +
      "Enough for territory and species filtering; never enough to name a " +
      "street.",
  },
  {
    key: "region",
    label: "Region only",
    detail:
      "No coordinates are recorded at all. Nothing to reveal later, at the cost " +
      "of mapping and per-territory comparison.",
  },
];

/** True when the phone should ask for a GPS fix at all. */
export function wantsFix(precision: LocationPrecision): boolean {
  return precision !== "region";
}

/** The radii on offer, in miles. A short list because it is a grouping choice,
 *  not a dial — every value is one more cell size territory work has to bin. */
export const FUZZ_MILES_CHOICES = [1, 5, 10] as const;
export const DEFAULT_FUZZ_MILES = 5;

const MILES_PER_DEGREE_LAT = 69.0;

/**
 * A coordinate coarsened to "within N miles", by snapping to a grid.
 *
 * A grid, deliberately not random jitter. Jitter fails exactly the person it
 * protects: fifty captures at home, each displaced independently, average
 * straight back to the house. Snapping maps every point in a cell to the same
 * public point, so the hundredth capture says nothing the first did not.
 *
 * The cell is N miles on a side and the published point is its centre, so the
 * true location is never more than half a diagonal away — about 0.7 × N miles,
 * which keeps "within N miles" honest. The longitude grid is sized from the
 * *snapped* latitude, so every point in one latitude band shares one longitude
 * grid; sizing it from the raw latitude would give near-neighbours slightly
 * different cells, and the averaging leak would be back through the gap.
 *
 * Mirrored in fieldserver/core/coords.py, whose backstop re-snaps whatever
 * arrives — snapping a cell centre returns the same centre, so the two
 * implementations agree on already-snapped input.
 */
export function fuzzedCoords(
  latitude: number,
  longitude: number,
  miles: number = DEFAULT_FUZZ_MILES,
): { latitude: number; longitude: number } {
  const latCell = miles / MILES_PER_DEGREE_LAT;
  const snappedLat = (Math.floor(latitude / latCell) + 0.5) * latCell;
  const stretch = Math.max(Math.cos((snappedLat * Math.PI) / 180), 0.01);
  const lonCell = miles / (MILES_PER_DEGREE_LAT * stretch);
  let snappedLon = (Math.floor(longitude / lonCell) + 0.5) * lonCell;
  if (snappedLon > 180) snappedLon -= 360;
  if (snappedLon < -180) snappedLon += 360;
  return {
    latitude: Math.max(-90, Math.min(90, snappedLat)),
    longitude: snappedLon,
  };
}

/** True when coordinates may be shown — on the phone or anywhere downstream. */
/**
 * Whether coordinates may appear on a screen.
 *
 * Two independent questions, which is the whole point of the split: `precision`
 * says whether they were recorded, `censor` says whether they are shown. Both
 * have to agree before a coordinate is displayed, so a missing or unknown
 * `censor` masks rather than reveals.
 */
export function mayShowCoords(
  precision: LocationPrecision,
  censor?: boolean,
): boolean {
  if (precision !== "exact" && precision !== "fuzzed") return false;
  return censor === false;
}

/**
 * The coordinates a screen may draw for a capture, if any.
 *
 * At `fuzzed` these are the *snapped* coordinates — the same point the server
 * was sent — never the raw fix, which exists only in the local store. A screen
 * that showed the true fix would make every screenshot sharper than the sync,
 * and the setting is a promise about both.
 */
export function displayCoords(
  capture: { latitude?: number; longitude?: number },
  precision: LocationPrecision,
  censor?: boolean,
  fuzzMiles?: number,
): { latitude: number; longitude: number } | undefined {
  if (!mayShowCoords(precision, censor)) return undefined;
  if (capture.latitude === undefined || capture.longitude === undefined) return undefined;
  if (precision === "fuzzed") {
    return fuzzedCoords(capture.latitude, capture.longitude, fuzzMiles);
  }
  return { latitude: capture.latitude, longitude: capture.longitude };
}

/**
 * A region as this app writes one: "Utah, US", "Nordrhein-Westfalen, DE".
 *
 * Region and country, nothing finer. A city is already too small in a rural
 * area — "Alta, US" is a village of four hundred people — and the question the
 * corpus asks of place at this level is which population was recorded.
 */
export function formatRegion(
  parts: { region?: string | null; country?: string | null; isoCountryCode?: string | null },
): string | undefined {
  const region = parts.region?.trim();
  const country = (parts.isoCountryCode ?? parts.country)?.trim();
  if (!region) return country || undefined;
  return country ? `${region}, ${country}` : region;
}

/**
 * What to print for a capture's place.
 *
 * One function, used by every screen that shows a location, because "we masked
 * it in three places and forgot the fourth" is how this feature fails. The
 * fourth was going to be the map callout.
 */
export function describePlace(
  capture: { latitude?: number; longitude?: number; region?: string },
  precision: LocationPrecision,
  censor?: boolean,
  fuzzMiles?: number,
): string | undefined {
  const coords = displayCoords(capture, precision, censor, fuzzMiles);
  if (coords) {
    // Two decimals at fuzzed, not four: a cell centre printed to eleven metres
    // would claim a precision the point does not have.
    if (precision === "fuzzed") {
      return `≈ ${coords.latitude.toFixed(2)}, ${coords.longitude.toFixed(2)}`;
    }
    return `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`;
  }
  return capture.region;
}

/**
 * The coordinates that may be sent for a capture.
 *
 * The one place the decision is made, and it is made on the way out rather than
 * on the way in: a recordist who tightens the setting today should stop sending
 * coordinates for captures already sitting in the queue, which is exactly what
 * they would expect and not what "filter at record time" alone would do.
 */
export function coordsToSend(
  capture: { latitude?: number; longitude?: number },
  precision: LocationPrecision,
  fuzzMiles?: number,
): { latitude?: number; longitude?: number } {
  if (precision === "region") return {};
  if (precision === "fuzzed") {
    if (capture.latitude === undefined || capture.longitude === undefined) return {};
    return fuzzedCoords(capture.latitude, capture.longitude, fuzzMiles);
  }
  return { latitude: capture.latitude, longitude: capture.longitude };
}

/**
 * Why a sync should not run yet, if anything.
 *
 * At `region` precision the region is not a nicety — it is the *only* thing a
 * capture says about where it was, and a corpus of recordings that name no
 * place at all is one where the population cannot be identified afterwards. So
 * the sync waits rather than quietly uploading rows that can never be grouped.
 *
 * Deliberately only at that setting. With coordinates recorded there is always
 * something to fall back on, and blocking a sync over a blank field would be
 * pedantry rather than protection.
 */
export function blockedFromSyncing(settings: {
  locationPrecision: LocationPrecision;
  homeRegion: string;
}): string | undefined {
  if (settings.locationPrecision !== "region") return undefined;
  if (settings.homeRegion.trim()) return undefined;
  return "Set your region in Settings first — with no coordinates recorded, it is the only thing saying where a capture was.";
}
