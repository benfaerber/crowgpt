import { useState } from "react";

import type { FleetCapture } from "../api/types";
import { CaptureDetail } from "./CaptureDetail";
import { CapturesTable } from "./CapturesTable";

/**
 * Captures, and nothing else.
 *
 * The overview had grown to a dozen panels with the capture table somewhere in
 * the middle and its detail card underneath all of them, so opening a recording
 * meant clicking a row and then scrolling past every remaining row to read the
 * answer. Here the list is the whole page and the detail opens where the row is.
 */
export function CapturesPage({
  captures,
  loading,
}: {
  captures: FleetCapture[];
  loading: boolean;
}) {
  const [openId, setOpenId] = useState<number>();

  return (
    <div className="card">
      <h2>
        Captures
        {captures.length > 0 ? (
          <span className="muted"> · {captures.length}</span>
        ) : null}
      </h2>
      <CapturesTable
        captures={captures}
        loading={loading}
        selectedId={openId}
        onSelect={(id) => setOpenId((current) => (current === id ? undefined : id))}
        renderExpanded={(capture) => <CaptureDetail captureId={capture.id} inline />}
      />
    </div>
  );
}
