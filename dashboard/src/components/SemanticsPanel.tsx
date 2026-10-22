import type { CallContextMatrix } from "../api/types";

/** One cell: how many calls, and — the number that decides anything — how many
 *  separate recordings they came from. */
type Cell = { n: number; captures: number };

/** Below this a cell cannot be learned from, whatever its call count.
 *
 *  Grouped cross-validation holds out whole recordings, because two caws from
 *  one bout are nearly the same data point. A cell drawn from three captures
 *  has three independent observations no matter how many calls are in it, and
 *  experiments/0006 refuses to report a number below four. Marking those here
 *  is what turns "we have eight of those" into "go get that one again on a
 *  different day". */
const MIN_CAPTURES = 4;

/**
 * Which calls co-occur with which witnessed situations.
 *
 * The question the whole project is for, and the only view here that could ever
 * answer it. Deliberately blunt: this is co-occurrence, not inference. A crow
 * calling while a dog is present is not necessarily calling *about* the dog,
 * and at this corpus size the honest reading is "where should I record next",
 * not "here is what a rattle means".
 *
 * Human labels only. Counting model detections would let the model's own bias
 * decide what a context sounds like, which is circular in exactly the direction
 * that matters.
 */
export function SemanticsPanel({ matrix }: { matrix?: CallContextMatrix }) {
  if (!matrix) return <div className="card muted">Loading…</div>;

  const {
    pairs,
    contexts,
    contexts_awaiting_labels: awaiting,
    silent_contexts: silent = [],
    silent_captures: silentCaptures = 0,
  } = matrix;
  // One matrix per species, because "alarm call" is a different vocalisation in
  // an American Crow and a hooded crow. Collapsing them into one table would
  // undo the separation the query goes to the trouble of making, and quietly:
  // the second species would simply overwrite the first in this map.
  const species = [...new Set(pairs.map((pair) => pair.species))].sort();
  const max = Math.max(1, ...pairs.map((pair) => pair.n));

  return (
    <div className="card">
      <h2>Calls × context</h2>
      <p className="muted" style={{ fontSize: ".82rem", marginTop: 0 }}>
        Confirmed calls in captures tagged with each situation. Co-occurrence,
        not meaning — a crow calling while a dog is there is not necessarily
        calling about the dog.{" "}
        {matrix.kept_only
          ? "Counts only captures marked as real observations; seeded and test material is excluded."
          : "Counting everything, including seeded and test material — this describes the pipeline, not crows."}
      </p>
      <p className="muted" style={{ fontSize: ".78rem", marginTop: "-.4rem" }}>
        Each cell reads <strong>calls/captures</strong>. The second number is the
        one that decides whether a cell can be learned from — eight calls from
        one morning is one observation repeated, and a <strong>!</strong> marks
        a cell under {MIN_CAPTURES} separate recordings. Those are where to point
        the next session.
      </p>

      {/* The denominator, stated next to the numerator on purpose. A matrix of
          co-occurrences with no control group reads as a result; sitting beside
          the count of times the same situation produced silence, it reads as
          what it is. */}
      {silentCaptures > 0 ? (
        <div className="note" style={{ marginBottom: ".8rem" }}>
          <strong>{silentCaptures}</strong> recording(s) confirmed to hold no calls
          {silent.length > 0 ? (
            <>
              {" — during: "}
              {silent.map((row, i) => (
                <span key={row.key}>
                  {i > 0 ? ", " : ""}
                  {row.key.replace(/_/g, " ")} (×{row.captures})
                </span>
              ))}
            </>
          ) : null}
          . These are the control group: the same situation, and nobody called.
        </div>
      ) : (
        <div className="note" style={{ marginBottom: ".8rem" }}>
          No confirmed-silent recordings yet. Without them these counts have no
          denominator — they say what was happening when a crow called, never how
          often it happened and none did.
        </div>
      )}

      {contexts.length === 0 ? (
        <div className="note">
          Nothing tagged yet. Tag what was happening in the field app, confirm the
          calls, and this fills in.
        </div>
      ) : pairs.length === 0 ? (
        <div className="note">
          {contexts.length} capture(s) tagged with a situation, but no calls
          confirmed yet — so there is nothing to pair them with. Confirming those
          is what turns this into an answer.
        </div>
      ) : (
        species.map((bird) => {
          const mine = pairs.filter((pair) => pair.species === bird);
          const callTypes = [...new Set(mine.map((pair) => pair.call_type))].sort();
          // Calls AND the captures they came from. The call count alone is the
          // most misleading number on this page: eight alarm calls at a loud
          // worker reads as a finding until you notice all eight are one
          // morning, and a model grouped by recording would hold that whole
          // cell out in a single fold.
          const byContext = new Map<string, Map<string, Cell>>();
          for (const pair of mine) {
            const row = byContext.get(pair.context_key) ?? new Map<string, Cell>();
            row.set(pair.call_type, { n: pair.n, captures: pair.captures });
            byContext.set(pair.context_key, row);
          }
          const seen = contexts.filter((context) => byContext.has(context.key));
          return (
            <div key={bird} style={{ marginBottom: "1rem" }}>
              {/* Named even when there is only one, so a second species
                  appearing is a new table rather than a silent change of
                  meaning in an existing one. */}
              <h3 style={{ fontSize: ".8rem", margin: "0 0 .4rem", opacity: 0.8 }}>
                {bird}
              </h3>
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Situation</th>
                      {callTypes.map((callType) => (
                        <th key={callType} className="num">
                          {callType}
                        </th>
                      ))}
                      <th className="num">Captures</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seen.map((context) => {
                      const row = byContext.get(context.key);
                      return (
                        <tr key={context.key}>
                          <td>{context.key.replace(/_/g, " ")}</td>
                          {callTypes.map((callType) => {
                            const cell = row?.get(callType);
                            const n = cell?.n ?? 0;
                            const captures = cell?.captures ?? 0;
                            const thin = n > 0 && captures < MIN_CAPTURES;
                            return (
                              <td
                                key={callType}
                                className="num"
                                // Weight rather than colour: the interesting cell
                                // is the one that stands out from its row, and a
                                // heat scale over counts this small invents
                                // confidence.
                                style={{
                                  opacity: n === 0 ? 0.25 : 0.5 + (n / max) * 0.5,
                                  fontWeight: n === max && n > 0 ? 700 : 400,
                                }}
                                title={
                                  n === 0
                                    ? undefined
                                    : `${n} call(s) across ${captures} capture(s)` +
                                      (thin
                                        ? ` — under ${MIN_CAPTURES}, so recording identity` +
                                          ` and situation cannot be told apart yet`
                                        : "")
                                }
                              >
                                {n || "·"}
                                {n > 0 ? (
                                  <span
                                    className="muted"
                                    style={{
                                      fontSize: ".72em",
                                      marginLeft: ".25em",
                                      // Thin cells are the ones to go record, so
                                      // they must not read as quiet detail.
                                      opacity: thin ? 1 : 0.55,
                                    }}
                                  >
                                    /{captures}
                                    {thin ? "!" : ""}
                                  </span>
                                ) : null}
                              </td>
                            );
                          })}
                          <td className="num muted">{context.captures}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })
      )}

      {awaiting > 0 ? (
        <div className="note">
          {awaiting} tagged capture(s) have no confirmed calls yet — those are the
          recordings whose meaning is still unread.
        </div>
      ) : null}
    </div>
  );
}
