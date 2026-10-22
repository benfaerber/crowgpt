import type { ContextEvent, FleetConfig, Label } from "../api/types";
import { colorForCall, colorForContext, contextText, labelText } from "../vocab";
import { Pill } from "./detail-atoms";

/**
 * The human labels, each with the context witnessed against it — and, below,
 * the context that has no call attached. The two travel together because they
 * share the joining rule: context is per call, not per capture.
 */
export function LabelList({
  labels,
  context,
  config,
  silentConfirmedAt,
}: {
  labels: Label[];
  context: ContextEvent[];
  config: FleetConfig | undefined;
  silentConfirmedAt: string | null;
}) {
  return (
    <>
      {labels.length > 0 ? (
        <>
          <h2 style={{ marginTop: "1.2rem" }}>Human labels</h2>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Span</th>
                  <th>Species</th>
                  <th>Call type</th>
                  <th>Witnessed</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((label) => {
                  // Context is per call, not per capture — pairing every
                  // situation in a recording with every call in it is exactly
                  // what the matrix refuses to do, so the detail shows the
                  // same joining rule.
                  const witnessed = context.filter((e) => e.label_id === label.id);
                  return (
                    <tr key={label.id}>
                      <td className="muted">
                        {label.start_sec != null
                          ? `${label.start_sec.toFixed(1)}–${(label.end_sec ?? 0).toFixed(1)}s`
                          : "whole clip"}
                      </td>
                      <td>{label.species}</td>
                      <td>
                        <Pill color={colorForCall(config, label.call_type)}>
                          {labelText(config, label.call_type)}
                        </Pill>
                        {label.notes ? (
                          <div className="meta">{label.notes}</div>
                        ) : null}
                      </td>
                      <td>
                        {witnessed.length > 0 ? (
                          <div className="pills">
                            {witnessed.map((e) => (
                              <Pill key={e.id} color={colorForContext(config, e.key)}>
                                {contextText(config, e.key)}
                              </Pill>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="muted">
                        {label.label_source}
                        {label.config_version ? (
                          <span title="the vocabulary version this judgement was chosen from">
                            {" "}· v{label.config_version}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {/* Context with no label is not an orphan: on a confirmed-silent capture
          it is the control group — the situation happened and nothing was said.
          Attached rows are shown against their call above. */}
      {context.some((e) => e.label_id === null) ? (
        <>
          <h2 style={{ marginTop: "1.2rem" }}>Witnessed, with no call attached</h2>
          <div className="note" style={{ marginBottom: ".6rem" }}>
            {silentConfirmedAt
              ? "On a capture confirmed silent, this is the control the matrix counts against."
              : "Recorded against the capture rather than a call."}
          </div>
          {context
            .filter((e) => e.label_id === null)
            .map((event) => (
              <div className="obs" key={event.id}>
                <Pill color={colorForContext(config, event.key)}>
                  {contextText(config, event.key)}
                </Pill>
                {event.notes ? ` — ${event.notes}` : ""}
                {event.start_sec !== null ? (
                  <div className="meta">
                    {event.start_sec.toFixed(1)}–{(event.end_sec ?? 0).toFixed(1)}s
                  </div>
                ) : null}
              </div>
            ))}
        </>
      ) : null}
    </>
  );
}
