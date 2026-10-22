import { useFamilyDetail } from "../api/client";
import {
  formatConfidence,
  describePlaceForOperator,
  formatDuration,
  formatTime,
} from "../format";
import { FamilySwatch } from "./FamiliesPanel";
import { StatusPill } from "./StatusPill";

/**
 * One family, examined.
 *
 * The call-type breakdown is the part worth having: it is the first view whose
 * subject is a *family* rather than a clip, which is what a claim like "this is
 * family A in SLC" eventually has to be built on.
 */
export function FamilyDetail({ familyId }: { familyId: number }) {
  const { data, isPending, error } = useFamilyDetail(familyId);

  if (isPending) return <div className="card muted">Loading…</div>;
  if (error) {
    return (
      <div className="card">
        <div className="note">Failed to load — {error.message}</div>
      </div>
    );
  }

  const { family, captures, call_types: callTypes } = data;

  return (
    <div className="card">
      <h2>
        <FamilySwatch color={family.color} size={12} />
        {family.name}
        <span className="muted"> · {family.contributor_name ?? "—"}</span>
      </h2>
      {family.notes ? <div className="note">{family.notes}</div> : null}
      <div className="muted" style={{ fontSize: ".82rem" }}>
        {describePlaceForOperator(family)} · heard{" "}
        {formatTime(family.first_heard)} → {formatTime(family.last_heard)}
      </div>

      <h2 style={{ marginTop: "1.2rem" }}>
        Heard saying{" "}
        {callTypes.length === 0 ? (
          <span className="muted">(nothing analyzed yet)</span>
        ) : null}
      </h2>
      {callTypes.length > 0 ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Species</th>
                <th>Call type</th>
                <th className="num">Count</th>
                <th className="num">Mean conf.</th>
              </tr>
            </thead>
            <tbody>
              {callTypes.map((type) => (
                <tr key={`${type.species}/${type.call_type}`}>
                  <td>{type.species}</td>
                  <td>{type.call_type ?? "—"}</td>
                  <td className="num">{type.n}</td>
                  <td className="num">{formatConfidence(type.mean_confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <h2 style={{ marginTop: "1.2rem" }}>Captures ({captures.length})</h2>
      {captures.length === 0 ? (
        <div className="note">No captures assigned to this family yet.</div>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Recorded</th>
                <th>Status</th>
                <th className="num">Length</th>
                <th className="num">Calls</th>
                <th>Where</th>
              </tr>
            </thead>
            <tbody>
              {captures.map((capture) => (
                <tr key={capture.id}>
                  <td className="muted">#{capture.id}</td>
                  <td>{formatTime(capture.recorded_at ?? capture.created_at)}</td>
                  <td>
                    <StatusPill status={capture.status} />
                  </td>
                  {/* The server speaks seconds, the formatter milliseconds. */}
                  <td className="num">
                    {formatDuration(capture.duration_sec == null
                      ? null : capture.duration_sec * 1000)}
                  </td>
                  <td className="num">{capture.call_count ?? 0}</td>
                  <td className="muted">
                    {capture.location_name ??
                      describePlaceForOperator(capture)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
