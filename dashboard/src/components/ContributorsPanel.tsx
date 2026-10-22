import type { Contributor } from "../api/types";
import { formatTime } from "../format";

/**
 * People, not handsets.
 *
 * This listed one row per device once, which made a single recordist who had
 * reinstalled a few times look like six contributors. Devices are a detail *of*
 * a person; the panel beside this one shows them individually.
 */
export function ContributorsPanel({ contributors }: { contributors: Contributor[] }) {
  return (
    <div className="card">
      <h2>Contributors</h2>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Person</th>
              <th>Devices</th>
              <th className="num">Captures</th>
              <th className="num">Labels</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {contributors.map((person) => {
              const named = person.device_labels ? person.device_labels.split(", ") : [];
              const unnamed = person.device_count - named.length;
              const devices =
                [person.device_labels, unnamed > 0 ? `${unnamed} unnamed` : ""]
                  .filter(Boolean)
                  .join(", ") || "—";
              return (
                <tr key={person.id}>
                  <td>
                    {person.display_name}
                    {person.role !== "contributor" ? (
                      <span className="muted"> ({person.role})</span>
                    ) : null}
                    {person.status === "suspended" ? (
                      <span className="muted"> · suspended</span>
                    ) : null}
                  </td>
                  <td className="muted">{devices}</td>
                  <td className="num">{person.capture_count}</td>
                  <td className="num">{person.label_count}</td>
                  <td className="muted">{formatTime(person.last_seen_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
