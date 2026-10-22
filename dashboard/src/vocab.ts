/**
 * The served vocabulary, turned into the words and colours a page shows.
 *
 * The phone renders the same three things — a call type's colour, its display
 * text, and a context chip's text — from the same `/api/config`. A rattle that
 * is amber on the phone and blue on the dashboard is a real bug in a labelling
 * tool, and nothing but a shared source prevents it. This is the dashboard's
 * half of that; `mobile/src/domain/config.ts` is the phone's.
 *
 * Everything here degrades to the raw key rather than throwing. The config is
 * fetched, so a page can render before it lands or after it fails, and a table
 * of keys is worth more than a blank one.
 */

import type { FleetConfig } from "./api/types";

/**
 * Unclassified. Grey on purpose rather than borrowing another type's colour,
 * which would imply a classification we do not have. The literal is the phone's
 * (`mobile/src/domain/config.ts`); keep them equal.
 */
export const UNTYPED = "#9aa5b1";

/**
 * A call type resolves to its *core* class's colour, so "mobbing" reads as the
 * alarm it maps to and the eye groups what the taxonomy groups.
 */
export function colorForCall(
  config: FleetConfig | undefined,
  callType?: string | null,
): string {
  if (!callType || !config) return UNTYPED;
  const core = config.labels.find((l) => l.key === callType)?.core ?? callType;
  return config.core_colors[core] ?? UNTYPED;
}

/** "alarm call" → "Alarm call". Falls back to the key, never to blank. */
export function labelText(
  config: FleetConfig | undefined,
  callType?: string | null,
): string {
  if (!callType) return "unlabelled";
  return config?.labels.find((l) => l.key === callType)?.text ?? callType;
}

/** "crows_agitated" → "Crows agitated". */
export function contextText(
  config: FleetConfig | undefined,
  key: string,
): string {
  return config?.contexts.find((c) => c.key === key)?.text ?? key.replace(/_/g, " ");
}

export function contextCategory(
  config: FleetConfig | undefined,
  key: string,
): string | undefined {
  return config?.contexts.find((c) => c.key === key)?.category;
}

/**
 * Chip colours by category.
 *
 * Mirrored from `mobile/src/ui/components/ContextTagger.tsx` rather than
 * served, because `/api/config` carries a category name per context and no
 * colour for it. That makes this the one place the two clients can drift on
 * purpose-built colour, so it is worth saying: if a category is recoloured on
 * the phone, change it here in the same commit, or move both to the config.
 *
 * Descriptive, never interpretive — the phone learned that when an earlier
 * version filed "human walks through" under "Threat", which answers the
 * question the corpus exists to ask, and gets it wrong for a recordist the
 * birds know.
 */
const CATEGORY_COLORS: Record<string, string> = {
  people: "#efb057",
  animals: "#f27070",
  food: "#6bd28a",
  crows: "#6ea8fe",
  quiet: "#9aa5b1",
};

export function colorForContext(
  config: FleetConfig | undefined,
  key: string,
): string {
  const category = contextCategory(config, key);
  return (category && CATEGORY_COLORS[category]) ?? UNTYPED;
}

/** "feeder" → "I've fed these crows". Served, so this cannot drift. */
export function observerRoleText(
  config: FleetConfig | undefined,
  key?: string | null,
): string | undefined {
  if (!key) return undefined;
  return config?.observer_roles?.find((r) => r.key === key)?.text
    ?? key.replace(/_/g, " ");
}

/**
 * Distance bands, mirrored from `mobile/src/domain/distance.ts`.
 *
 * Not served by `/api/config` — unlike the roles above, which is why those
 * cannot drift and these can. The dashboard previously rebuilt the label with
 * `.replace(/_/g," ").replace("m"," m")`, which turned `5_20m` into "5 20 m":
 * the en-dash gone and a range reading as two separate numbers. Worth serving
 * properly one day; until then keep this equal to the phone's list.
 */
const DISTANCE_LABELS: Record<string, string> = {
  under_5m: "Under 5 m",
  "5_20m": "5–20 m",
  "20_50m": "20–50 m",
  over_50m: "Over 50 m",
};

export function distanceLabel(key?: string | null): string | undefined {
  if (!key) return undefined;
  return DISTANCE_LABELS[key] ?? key.replace(/_/g, " ");
}
