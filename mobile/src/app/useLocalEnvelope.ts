import { useEffect, useState } from "react";

import type { CaptureRecord } from "../domain/types";
import { computeWavEnvelope } from "../sync/wavEnvelope";
import type { AppServices } from "./AppServices";
import { log } from "./Log";

/**
 * The capture's own waveform, read off the phone.
 *
 * Until now the trace came back from the server's analysis, so an unsynced
 * recording showed a blank rectangle — no way to see what you had recorded, and
 * nothing to crop against. This computes it locally the first time a capture is
 * opened and stores it, since scanning a multi-megabyte file on every visit
 * would be wasteful and visibly slow.
 */
export function useLocalEnvelope(
  services: AppServices,
  capture: CaptureRecord,
): { peaks: number[]; durationSec?: number; computing: boolean } {
  const [peaks, setPeaks] = useState<number[]>(() => parseEnvelope(capture.envelopeJson));
  const [durationSec, setDurationSec] = useState<number | undefined>();
  const [computing, setComputing] = useState(false);

  useEffect(() => {
    if (capture.envelopeJson || !capture.audioPath) return;
    let live = true;
    setComputing(true);
    void computeWavEnvelope(services.rawMedia, capture.audioPath)
      .then(async (envelope) => {
        if (!live) return;
        setPeaks(envelope.peaks);
        setDurationSec(envelope.durationSec);
        // The write's failure is logged apart from the compute's silence
        // below: a store that keeps refusing re-runs the multi-megabyte scan
        // on every visit, which is the exact cost storing it exists to avoid
        // — and it was invisible, because the trace still rendered.
        await services.repository
          .update(capture.uuid, { envelopeJson: JSON.stringify(envelope.peaks) })
          .catch((failure) =>
            log.warn("capture", "could not store the waveform envelope", failure));
      })
      // A capture whose file has gone is still worth showing; it just has no trace.
      .catch(() => undefined)
      .finally(() => live && setComputing(false));
    return () => {
      live = false;
    };
  }, [capture.audioPath, capture.envelopeJson, capture.uuid, services]);

  return { peaks, durationSec, computing };
}

/** A truncated envelope column must not crash the detail screen at render. */
function parseEnvelope(json: string | undefined): number[] {
  if (!json) return [];
  try {
    return JSON.parse(json) as number[];
  } catch {
    return [];
  }
}
