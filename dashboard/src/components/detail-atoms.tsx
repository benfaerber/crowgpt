/**
 * A tinted chip, the dashboard's echo of the phone's call buttons and context
 * chips. The hue is the vocabulary's; only the shape is the stylesheet's.
 */
export function Pill({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span className="pill" style={{ color, backgroundColor: `${color}22` }}>
      <span>{children}</span>
    </span>
  );
}

/**
 * The first line's worth of a note, for the collapsed summary.
 *
 * Enough to tell one span's note from another's without opening it. Cut on a
 * word so a truncated sentence still reads as prose rather than as corruption,
 * and newlines flattened because a summary is one line whatever the body does.
 */
export function preview(text: string, limit = 90): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= limit) return flat;
  const cut = flat.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > 40 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

/** One labelled fact in the block under a capture's title. */
export function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
