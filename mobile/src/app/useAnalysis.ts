import { useCallback, useEffect, useRef, useState } from "react";

import type { CaptureRecord } from "../domain/types";
import { isStaleServerLink } from "../net/HttpClient";
import type { DetectedCall } from "../net/serverTypes";
import type { AppServices } from "./AppServices";
import { log } from "./Log";

export interface AnalysisView {
  calls: DetectedCall[];
  /** Envelope for the timeline, 0..1 per bucket. Empty until analyzed. */
  waveform: number[];
  /** Server-measured duration in seconds; the local one is a fallback. */
  duration?: number;
  /** True while a job is queued or running server-side. */
  working: boolean;
  /**
   * When these results were last fetched, set only while they are the cached
   * copy rather than a fresh answer. What the screen says instead of pretending
   * the server confirmed something it was never asked.
   */
  cachedAt?: string;
  status?: string;
  error?: string;
  requestAnalysis: () => Promise<void>;
}

const POLL_MS = 2000;

/**
 * Watches the server-side analysis for one capture.
 *
 * Inference runs in a separate worker off a shared queue, so results arrive
 * whenever they arrive — the app polls rather than waiting on the request that
 * enqueued the job. Nothing here works until the capture has synced, because
 * until then the server has no audio to analyze.
 */
export function useAnalysis(services: AppServices, capture: CaptureRecord): AnalysisView {
  const [calls, setCalls] = useState<DetectedCall[]>([]);
  const [waveform, setWaveform] = useState<number[]>([]);
  const [duration, setDuration] = useState<number | undefined>();
  const [cachedAt, setCachedAt] = useState<string | undefined>();
  const [working, setWorking] = useState(false);
  const [status, setStatus] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const jobId = useRef<number | undefined>(undefined);
  const canceled = useRef(false);

  useEffect(() => {
    canceled.current = false;
    return () => {
      canceled.current = true;
    };
  }, []);

  const loadCalls = useCallback(async () => {
    // The stored copy first, and without waiting on the network. This is the
    // whole point of keeping one: in a park the server is a laptop on a home
    // network, and the request below is going to fail.
    // A read failure is logged before it becomes a miss: the offline story in
    // the park depends entirely on this cache, and a store that always throws
    // used to be indistinguishable from one that was simply never filled.
    const cached = await services.analysisCache?.get(capture.uuid).catch((failure) => {
      log.warn("analysis", "could not read the cached analysis", failure);
      return undefined;
    });
    if (cached && !canceled.current) {
      setCalls(cached.calls);
      setWaveform(cached.waveform);
      setDuration(cached.duration);
      setCachedAt(cached.fetchedAt);
    }
    if (capture.serverCaptureId === undefined) return;
    try {
      const found = await services.fieldServer.analysis(capture.serverCaptureId);
      if (!canceled.current) {
        setCalls(found.calls);
        setWaveform(found.waveform ?? []);
        setDuration(found.duration);
        setCachedAt(undefined);
        setError(undefined);
      }
      // Written down even when nothing came back: "the server has analyzed this
      // and found nothing" is an answer, and showing last week's calls next to
      // it would be a lie of exactly the kind a cache is prone to.
      await services.analysisCache?.save(capture.uuid, {
        calls: found.calls,
        waveform: found.waveform ?? [],
        duration: found.duration,
      }).catch((failure) =>
        log.warn("analysis", "could not cache the analysis for offline", failure));
    } catch (failure) {
      if (canceled.current) return;
      if (isStaleServerLink(failure)) {
        // This capture points at a row minted under a previous enrollment, so
        // the server is right to refuse it. Drop the dead link; the next sync
        // re-creates it under the identity this device actually has.
        await services.repository.update(capture.uuid, {
          serverCaptureId: undefined,
          serverMediaId: undefined,
          uploadedBytes: 0,
          syncState: "local",
          syncedAt: undefined,
        });
        setError("Uploaded under a previous enrollment — sync again to restore it.");
        return;
      }
      // Unreachable with a stored copy on screen is not an error worth a red
      // line — the timeline is showing real results and the note above it
      // already says how old they are.
      if (cached) return;
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [capture.serverCaptureId, capture.uuid, services]);

  useEffect(() => {
    void loadCalls();
  }, [loadCalls]);

  /**
   * Poll until the job stops moving.
   *
   * Written as "keep going only while it is still in flight" rather than
   * "stop on the states I know about": a state this build doesn't recognize is
   * a server that has moved on, and spinning forever is the worst possible
   * reading of it. That is not hypothetical — the worker used to write 'error'
   * where the client looked for 'failed', and a failed analysis left the screen
   * working forever with no way to find out why.
   */
  const poll = useCallback(async () => {
    while (!canceled.current && jobId.current !== undefined) {
      const job = await services.fieldServer.job(jobId.current);
      if (canceled.current) return;
      setStatus(job.state);
      if (job.state === "queued" || job.state === "running") {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        continue;
      }
      jobId.current = undefined;
      if (job.state === "done") {
        await loadCalls();
      } else {
        setError(job.error ?? `analysis ${job.state}`);
      }
      setWorking(false);
      return;
    }
  }, [loadCalls, services]);

  const requestAnalysis = useCallback(async () => {
    if (capture.serverCaptureId === undefined) {
      setError("Sync this capture before analyzing it");
      return;
    }
    setError(undefined);
    setWorking(true);
    try {
      const job = await services.fieldServer.requestAnalysis(capture.serverCaptureId);
      jobId.current = job.id;
      setStatus(job.state);
      await poll();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setWorking(false);
    }
  }, [capture.serverCaptureId, poll, services]);

  return { calls, waveform, duration, working, cachedAt, status, error, requestAnalysis };
}
