import type { LabelTotal } from "../api/types";

/** What the corpus actually contains, by call type — the retrain view. */
export function LabelTotals({ totals }: { totals: LabelTotal[] }) {
  const max = Math.max(1, ...totals.map((total) => total.n));
  return (
    <div className="card">
      <h2>Label totals</h2>
      {totals.length === 0 ? (
        <div className="note">
          No human labels yet — this is the corpus the retrain reads.
        </div>
      ) : (
        <div className="bars">
          {totals.map((total) => (
            <div className="bar" key={`${total.species}/${total.call_type}`}>
              <div className="name">
                {total.call_type} <span className="muted">{total.species}</span>
              </div>
              <div className="track">
                <div className="fill" style={{ width: `${(total.n / max) * 100}%` }} />
              </div>
              <div className="v">{total.n}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
