/**
 * The tall-trees layer — scouting data for finding new crows.
 *
 * Server-published (experiment 0083's canopy analysis today), fetched like
 * the fleet config: once per launch, best-effort, cached so a park with no
 * signal still shows the layer. The server's GeoJSON is normalised here into
 * a flat domain shape so the map page never parses GeoJSON.
 */

export interface TreeStand {
  latitude: number;
  longitude: number;
  /** Canopy height in metres — the reason the stand is on the map. */
  heightM: number;
  areaM2: number;
}

export interface TreeLayer {
  stands: TreeStand[];
}

interface GeojsonFeature {
  geometry?: { type?: string; coordinates?: [number, number] };
  properties?: { h?: number; area_m2?: number };
}

/** Normalise the server payload, dropping anything malformed rather than
 *  throwing — one odd feature must not cost the other 2,499. */
export function treeLayerFromGeojson(payload: {
  features?: GeojsonFeature[];
}): TreeLayer {
  const stands: TreeStand[] = [];
  for (const feature of payload.features ?? []) {
    const coords = feature.geometry?.coordinates;
    const h = feature.properties?.h;
    if (
      feature.geometry?.type !== "Point" ||
      !Array.isArray(coords) ||
      typeof coords[0] !== "number" ||
      typeof coords[1] !== "number" ||
      typeof h !== "number"
    ) {
      continue;
    }
    stands.push({
      longitude: coords[0],
      latitude: coords[1],
      heightM: h,
      areaM2: feature.properties?.area_m2 ?? 0,
    });
  }
  return { stands };
}

/** The 0083 map's height ramp, kept identical so the phone and the desktop
 *  map read as the same instrument. */
export function treeColor(heightM: number): string {
  if (heightM >= 30) return "#7b1fa2";
  if (heightM >= 25) return "#c2185b";
  if (heightM >= 21) return "#e64a19";
  return "#f9a825";
}
