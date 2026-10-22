import { useRelabelQueue } from "../api/client";
import { formatTime } from "../format";

/**
 * Labels whose vocabulary moved after they were made.
 *
 * Deliberately small and deliberately present when empty. "Nothing to revisit"
 * is the answer almost every day, and a panel that appears only when there is
 * a problem is one nobody trusts to be working — the reassuring reading has to
 * be visible for the alarming one to mean anything.
 *
 * The question is only answerable because each label records which version of
 * the vocabulary it was chosen from. Labels made before that stamp existed are
 * not counted here, because there is no honest way to place them.
 */
export function RelabelPanel({ signedIn }: { signedIn: boolean }) {
  const queue = useRelabelQueue(signedIn);
  const rows = queue.data ?? [];

  return (
    <div className="card">
      <h2>
        Relabel queue
        {rows.length > 0 ? <span className="pill s-queued"> {rows.length}</span> : null}
      </h2>

      {queue.isPending ? (
        <div className="muted">Checking…</div>
      ) : rows.length === 0 ? (
        <div className="muted">
          Nothing to revisit — every label was made under a vocabulary that still
          means what it did.
        </div>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Capture</th>
                <th>Labelled</th>
                <th>Made at</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>#{row.capture_id}</td>
                  <td>{row.call_type}</td>
                  {/* The vocabulary version, not the date: the date is what
                      cannot answer this question, since phones label offline
                      against whatever they last fetched. */}
                  <td className="muted" title={formatTime(row.created_at)}>
                    config v{row.config_version}
                  </td>
                  <td className="muted">{row.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
