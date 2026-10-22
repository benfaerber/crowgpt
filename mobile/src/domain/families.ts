/**
 * A named group of crows a recordist follows over time.
 *
 * Families are local-first like captures: created in the field with no signal
 * and pushed on the next sync, so `uuid` is the identity that matters and the
 * server id is bookkeeping. They belong to the device that made them — two
 * people watching "the pair on the corner" mean different birds.
 *
 * Individual crows are not modelled yet. When they are they hang off a family
 * (the shape is `crows(name, role, family_id)`), which is why the
 * capture points at a family rather than the other way round.
 */
export interface FamilyRecord {
  uuid: string;
  name: string;
  /** Hex, chosen once at creation, used as the glow behind the crow on the map. */
  color: string;
  notes?: string;
  createdAt: string;
  serverId?: number;
  syncedAt?: string;
}

/**
 * Colours for a new family.
 *
 * Fixed hues rather than a random RGB: a glow has to read against satellite
 * imagery that is mostly green, grey and brown, and randomly-generated colours
 * land on mud and foliage often enough to be useless. These are bright and
 * separable from each other and from the map.
 */
const FAMILY_COLORS = [
  "#7cc4ff", // sky
  "#ffd166", // amber
  "#06d6a0", // mint
  "#ef476f", // rose
  "#c58af9", // violet
  "#ff9f5a", // ember
  "#4dd6c8", // teal
  "#f4f1bb", // sand
];

/** Picks a colour not already in use, falling back to random once they run out. */
export function pickFamilyColor(taken: string[], random: () => number = Math.random): string {
  const free = FAMILY_COLORS.filter((c) => !taken.includes(c));
  const pool = free.length > 0 ? free : FAMILY_COLORS;
  return pool[Math.floor(random() * pool.length) % pool.length];
}
