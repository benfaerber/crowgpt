import type { Analysis, FleetConfig } from "../api/types";
import { formatConfidence } from "../format";
import { colorForCall, labelText } from "../vocab";
import { Pill } from "./detail-atoms";

/** What the analyzer found: the detections table under a capture. */
export function DetectedCalls({
  analysis,
  config,
}: {
  analysis: Analysis | null;
  config: FleetConfig | undefined;
}) {
  const calls = analysis?.calls ?? [];
  return (
    <>
      <h2 style={{ marginTop: "1.2rem" }}>
        Detected calls {calls.length === 0 ? <span className="muted">(none)</span> : null}
        {analysis?.model_version ? (
          <span className="muted" style={{ textTransform: "none" }}>
            {" "}· {analysis.model_version}
          </span>
        ) : null}
      </h2>
      {calls.length > 0 ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Span</th>
                <th>Species</th>
                <th>Call type</th>
                <th className="num">Confidence</th>
                <th className="num">Crow</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call, index) => (
                // A candidate is sub-threshold and counted as nothing until a
                // human rules on it. Rendered identically to a confirmed
                // detection it launders into fact, which is the loop
                // experiment 0004 exists to break — so it is said in words,
                // not by a shade of grey.
                <tr key={index} className={call.candidate ? "muted" : undefined}>
                  <td className="muted">
                    {call.start_sec.toFixed(1)}–{call.end_sec.toFixed(1)}s
                  </td>
                  <td title={call.scientific_name ?? undefined}>{call.species}</td>
                  <td>
                    {call.call_type ? (
                      <Pill color={colorForCall(config, call.call_type)}>
                        {labelText(config, call.call_type)}
                      </Pill>
                    ) : (
                      "—"
                    )}
                    {call.candidate ? (
                      <span
                        className="tag"
                        title="Sub-threshold — offered for a human to rule on, counted as nothing until then"
                        style={{ marginLeft: ".4rem" }}
                      >
                        candidate
                      </span>
                    ) : null}
                    {/* The second call in a span, which the analyzer used to
                        drop on the floor. Shown under the top answer rather
                        than beside it: it is a weaker claim, and on a softmax
                        head it is a weaker claim still — "torn" rather than
                        "heard two things" — so the wording changes with it. */}
                    {call.alternates?.length ? (
                      <div
                        className="muted"
                        style={{ fontSize: ".76rem", marginTop: ".2rem" }}
                        title={
                          call.multi_label
                            ? "Independent probabilities — the head heard these too"
                            : "A softmax runner-up: the head was torn between these, not hearing both"
                        }
                      >
                        {call.multi_label ? "also heard" : "or maybe"}{" "}
                        {call.alternates
                          .map(
                            (alt) =>
                              `${labelText(config, alt.call_type)} ${formatConfidence(
                                alt.confidence,
                              )}`,
                          )
                          .join(", ")}
                      </div>
                    ) : null}
                  </td>
                  <td className="num">{formatConfidence(call.confidence)}</td>
                  <td className="num">{formatConfidence(call.crow_conf)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
