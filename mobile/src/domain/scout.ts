/**
 * The scouting layer — 0084's ranked targets for finding new crow families,
 * and the Great Horned Owl sightings that subtract from the score.
 *
 * Fetched and cached like the trees layer: once per launch, best-effort,
 * held offline. Normalised here so the map page never parses the server
 * shape.
 */

export interface ScoutTarget {
  rank: number;
  latitude: number;
  longitude: number;
  score: number;
  /** Region slug ("slc-valley") — the county filter's handle. Empty on
   *  layers published before regions existed. */
  region: string;
  /** Nearest named greenspace, when one is within a short walk. */
  near: string;
  /** 0..1 per signal — why this cell scored. */
  signals: Record<string, number>;
}

export interface OwlSighting {
  latitude: number;
  longitude: number;
  region: string;
}

export interface PredatorSighting {
  latitude: number;
  longitude: number;
  species: string;
  /** Key into ScoutLayer.icons; falls back to the plain dot when absent. */
  icon: string;
  /** Someone else's sighting (iNaturalist), drawn dimmer than Ben's own. */
  community: boolean;
  /** ISO date the bird was observed, when the source recorded one. */
  date: string;
  /** Photo URL on iNat's CDN, loaded lazily when the popup opens; the
   *  server archives its own copy for the record. */
  photo: string;
  /** Observer login (iNat) or source name (eBird) — attribution, and the
   *  observer-bias tell. */
  by: string;
  /** Birds counted at once, when the source counts (eBird's howMany). */
  count: number;
  region: string;
}

export interface ScoutLayer {
  /** The counties the layer covers, for the map's filter. Empty means the
   *  layer predates regions and everything simply shows. */
  regions: { slug: string; name: string }[];
  targets: ScoutTarget[];
  owls: OwlSighting[];
  /** Per-species predator points, when the published layer carries them. */
  predators: PredatorSighting[];
  /** Icon name -> data URI, shipped inside the layer so icon changes are a
   *  republish, never an app rebuild. */
  icons: Record<string, string>;
  /** TRAX track segments in their route's own color — reference geometry
   *  for getting one's bearings, drawn under everything else. */
  rail: { color: string; coords: [number, number][]; region: string }[];
}

export function scoutLayerFromServer(payload: {
  regions?: unknown[];
  targets?: unknown[];
  owls?: unknown[];
  predators?: unknown[];
  icons?: Record<string, unknown>;
  rail?: unknown[];
}): ScoutLayer {
  const regions: { slug: string; name: string }[] = [];
  for (const raw of payload.regions ?? []) {
    const r = raw as Record<string, unknown>;
    if (typeof r.slug === "string" && typeof r.name === "string") {
      regions.push({ slug: r.slug, name: r.name });
    }
  }
  const region = (row: Record<string, unknown>): string =>
    typeof row.region === "string" ? row.region : "";
  const targets: ScoutTarget[] = [];
  for (const raw of payload.targets ?? []) {
    const t = raw as Record<string, unknown>;
    if (typeof t.rank !== "number" || typeof t.lat !== "number" ||
        typeof t.lon !== "number" || typeof t.score !== "number") {
      continue;
    }
    targets.push({
      rank: t.rank, latitude: t.lat, longitude: t.lon, score: t.score,
      region: region(t),
      near: typeof t.near === "string" ? t.near : "",
      signals: (t.signals as Record<string, number>) ?? {},
    });
  }
  const owls: OwlSighting[] = [];
  for (const raw of payload.owls ?? []) {
    const o = raw as Record<string, unknown>;
    if (typeof o.lat === "number" && typeof o.lon === "number") {
      owls.push({ latitude: o.lat, longitude: o.lon, region: region(o) });
    }
  }
  const predators: PredatorSighting[] = [];
  for (const raw of payload.predators ?? []) {
    const p = raw as Record<string, unknown>;
    if (typeof p.lat === "number" && typeof p.lon === "number"
        && typeof p.icon === "string") {
      predators.push({
        latitude: p.lat, longitude: p.lon, icon: p.icon,
        species: typeof p.species === "string" ? p.species : "",
        community: p.community === true,
        date: typeof p.date === "string" ? p.date : "",
        photo: typeof p.photo === "string" && p.photo.startsWith("https://")
          ? p.photo
          : "",
        by: typeof p.by === "string" ? p.by : "",
        count: typeof p.count === "number" ? p.count : 0,
        region: region(p),
      });
    }
  }
  const icons: Record<string, string> = {};
  for (const [key, value] of Object.entries(payload.icons ?? {})) {
    if (typeof value === "string" && value.startsWith("data:image/")) {
      icons[key] = value;
    }
  }
  const rail: { color: string; coords: [number, number][]; region: string }[] = [];
  for (const raw of payload.rail ?? []) {
    const s = raw as Record<string, unknown>;
    if (!Array.isArray(s.coords)) continue;
    const coords = s.coords.filter(
      (p): p is [number, number] =>
        Array.isArray(p) && typeof p[0] === "number" && typeof p[1] === "number",
    );
    if (coords.length < 2) continue;
    rail.push({
      color: typeof s.color === "string" && /^#[0-9a-fA-F]{3,8}$/.test(s.color)
        ? s.color
        : "#5c6bc0",
      coords,
      region: region(s),
    });
  }
  return { regions, targets, owls, predators, icons, rail };
}

/**
 * Spots from /api/scout/spots — ad-hoc circle queries. Same shape as
 * ranked targets, so the map renders them with the same vocabulary.
 */
export function scoutSpotsFromServer(
  payload: { spots?: unknown[] },
): ScoutTarget[] {
  const spots: ScoutTarget[] = [];
  for (const raw of payload.spots ?? []) {
    const t = raw as Record<string, unknown>;
    if (typeof t.rank !== "number" || typeof t.lat !== "number" ||
        typeof t.lon !== "number" || typeof t.score !== "number") {
      continue;
    }
    spots.push({
      rank: t.rank, latitude: t.lat, longitude: t.lon, score: t.score,
      region: typeof t.region === "string" ? t.region : "",
      near: typeof t.near === "string" ? t.near : "",
      signals: (t.signals as Record<string, number>) ?? {},
    });
  }
  return spots;
}
