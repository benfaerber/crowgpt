import type { DetectedCall } from "../net/serverTypes";

/** What the server said about one capture, the last time it was asked. */
export interface CachedAnalysis {
  calls: DetectedCall[];
  /** Envelope for the timeline, 0..1 per bucket. */
  waveform: number[];
  /** Server-measured, in seconds. More accurate than the local duration. */
  duration?: number;
  /** When this was fetched — the honest thing to show next to stale results. */
  fetchedAt: string;
}

/**
 * The last analysis the phone saw, kept on the phone.
 *
 * Detections live on the server because that is where BirdNET runs, and the app
 * fetched them fresh every time a capture was opened. That is exactly wrong for
 * the way this app is used: the recordist is in a park, the server is a laptop
 * on a home network, and the analysis is most wanted precisely when it cannot
 * be reached — "this new call sounds like the one marked alarm last week, is it
 * the same?" is a field question with no signal behind it.
 *
 * So results are written down as they arrive and read before the network is
 * consulted. What is shown is then never *less* than what was known, and going
 * out of range degrades a capture's timeline to slightly old rather than empty.
 *
 * A cache in the honest sense: nothing here is ground truth, none of it is
 * pushed anywhere, and losing it costs one fetch.
 */
export interface AnalysisCache {
  get(captureUuid: string): Promise<CachedAnalysis | undefined>;
  save(captureUuid: string, analysis: Omit<CachedAnalysis, "fetchedAt">): Promise<void>;
  forget(captureUuid: string): Promise<void>;
}
