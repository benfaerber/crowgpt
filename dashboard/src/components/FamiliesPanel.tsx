import type { Family } from "../api/types";
import { describePlaceForOperator, formatTime } from "../format";

/** A dot in the family's own colour, chosen on the phone and stored. */
export function FamilySwatch({ color, size = 10 }: { color: string | null; size?: number }) {
  if (!color) return null;
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: size / 2,
        background: color,
        boxShadow: `0 0 ${size * 0.6}px ${color}`,
        marginRight: ".45rem",
      }}
    />
  );
}

/**
 * Families, with the colour they were given in the field app.
 *
 * That colour is chosen once and stored, so a family looks the same here as it
 * does on the map on the phone — which is how you recognise one at a glance
 * without reading.
 */
export function FamiliesPanel({
  families,
  selectedId,
  onSelect,
}: {
  families: Family[];
  selectedId?: number;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="card">
      <h2>Families</h2>
      {families.length === 0 ? (
        <p className="muted" style={{ fontSize: ".85rem" }}>
          No families yet — they are created in the field app.
        </p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Family</th>
                <th>Where</th>
                <th className="num">Captures</th>
                <th className="num">Calls</th>
                <th>Last heard</th>
              </tr>
            </thead>
            <tbody>
              {families.map((family) => (
                <tr
                  key={family.id}
                  className={family.id === selectedId ? "row sel" : "row"}
                  onClick={() => onSelect(family.id)}
                >
                  <td>
                    <FamilySwatch color={family.color} />
                    {family.name}
                    <span className="muted"> · {family.contributor_name ?? "—"}</span>
                  </td>
                  <td className="muted">
                    {describePlaceForOperator(family)}
                  </td>
                  <td className="num">{family.capture_count}</td>
                  <td className="num">{family.call_count}</td>
                  <td className="muted">{formatTime(family.last_heard)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
