/**
 * Roughly how far away the bird was.
 *
 * A fixed list rather than a served vocabulary, unlike labels and contexts.
 * Those change as you discover what recurs; distance bands are physical, and
 * bounded by what a person can estimate looking at a bird. "About twenty
 * metres" is a real answer; metres to a decimal place would be invented
 * precision, and a slider would invite it.
 *
 * The bands are wide where estimation is hard. Nobody misjudges "within arm's
 * reach"; everybody misjudges fifty metres versus eighty, so those are one
 * band.
 *
 * Per capture rather than per call: it describes where you stood, and asking
 * again for every caw is a tap nobody takes.
 */
export interface DistanceBand {
  key: string;
  label: string;
  /** What it means in the field, for someone guessing. */
  hint: string;
}

export const DISTANCE_BANDS: DistanceBand[] = [
  { key: "under_5m", label: "Under 5 m", hint: "close enough to see its eye" },
  { key: "5_20m", label: "5–20 m", hint: "same tree, or across a garden" },
  { key: "20_50m", label: "20–50 m", hint: "across a street, or up a roofline" },
  { key: "over_50m", label: "Over 50 m", hint: "a speck, or out of sight" },
];

export function distanceLabel(key?: string): string | undefined {
  return DISTANCE_BANDS.find((band) => band.key === key)?.label;
}
