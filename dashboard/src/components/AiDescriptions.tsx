import type { AiDescription } from "../api/types";
import { formatTime } from "../format";
import { preview } from "./detail-atoms";

/** Machine-written prose about the recording — never rendered as testimony. */
export function AiDescriptions({ written }: { written: AiDescription[] }) {
  if (written.length === 0) return null;
  return (
    /* The whole block folds away too, and starts open. Two levels of
       collapse do different jobs: the inner ones keep any single note from
       running down the page, this one hides the machine's opinion entirely
       when you came to read the recordist. Open by default so a note is
       always one click away rather than two — hiding is the deliberate act
       here, not reading. */
    <details className="modelnotes" open>
      <summary>
        {/* Below the detections, and framed the same way. This is prose read
            off the same audio the detections came from — a second reading of
            the evidence, not a second witness. Placed above the recordist it
            would quietly invert the one rule that matters. */}
        <h2>What a model wrote</h2>
        <span className="count">
          {written.length} note{written.length === 1 ? "" : "s"}
        </span>
      </summary>
      <div className="note" style={{ marginBottom: ".6rem" }}>
        A guess, like the detections above — never ground truth, never
        training data, and never a substitute for an answer nobody gave.
      </div>
      {/* Collapsed by default, and each one its own <details> rather than a
          single toggle over the lot. These run to a couple of thousand
          characters each — a capture with eight spans buried the human
          labels below a screen and a half of machine prose, which is the
          wrong way round on a page whose whole argument is that the
          recordist outranks the model. The summary carries the span and the
          opening words, so the set stays scannable without opening any of
          them. Native <details>, so it needs no state and keeps working if
          JavaScript is having a bad day. */}
      {written.map((entry) => (
        <details className="obs" key={entry.id}>
          <summary>
            <span className="span">
              {entry.start_sec === null
                ? "whole recording"
                : `${entry.start_sec.toFixed(1)}–${(entry.end_sec ?? 0).toFixed(1)}s`}
            </span>
            <span className="peek">{preview(entry.description)}</span>
          </summary>
          {entry.description}
          <div className="meta">
            {entry.model ?? "unknown model"} · {formatTime(entry.written_at)}
          </div>
        </details>
      ))}
    </details>
  );
}
