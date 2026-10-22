import type { AnalysisCache } from "../data/AnalysisCache";
import type { CaptureRepository } from "../data/CaptureRepository";
import type { FieldServerClient } from "../net/FieldServerClient";

export interface PrefetchOutcome {
  /** Captures whose analysis is now stored on the phone. */
  stored: number;
  /** Synced captures the server had no analysis for yet. */
  pending: number;
  failed: number;
  /** True when it stopped at the ceiling rather than running out of captures. */
  truncated: boolean;
  /** True when it gave up because the server was plainly not there. */
  offline: boolean;
}

/**
 * A ceiling per run. The whole corpus is a few hundred captures and each answer
 * is a few kilobytes of JSON, so this is about not turning a sync into a long
 * silent stall rather than about size.
 */
const MAX_PER_RUN = 300;

/**
 * Consecutive failures that mean "there is no server", not "that one capture
 * went wrong".
 *
 * Without this, a phone out of range grinds through three hundred doomed
 * requests every time the app opens. Three rather than one because a single
 * failure is genuinely per-capture — a row minted under a previous enrollment
 * answers 404 while everything around it is fine.
 */
const GIVE_UP_AFTER = 3;

/**
 * Fill the analysis cache before it is needed, which is always somewhere else.
 *
 * Caching results as captures are opened is not enough on its own: it only ever
 * holds the captures already looked at while in range, and the ones wanted in
 * the field are the *old* ones — the point of having them there is to play a
 * call marked `alarm` in June against one recorded five minutes ago and decide
 * whether they are the same thing. A cache that fills on demand has nothing to
 * offer for that, because the demand happens where the server does not exist.
 *
 * So this pulls every synced capture's analysis while there is a network, on
 * the trip the phone was already making. It is a cache warm and nothing more:
 * it writes to no capture row, pushes nothing, and losing all of it costs one
 * run of this.
 *
 * Refetches rather than skipping what is already stored. Analysis is re-run
 * whenever the model or the thresholds change — which has happened repeatedly,
 * and each time the phone's copy silently became the old model's opinion.
 */
export class PrefetchAnalysis {
  constructor(
    private readonly repository: CaptureRepository,
    private readonly cache: AnalysisCache,
    private readonly client: FieldServerClient,
  ) {}

  async run(
    onProgress?: (done: number, total: number) => void,
  ): Promise<PrefetchOutcome> {
    const outcome: PrefetchOutcome = {
      stored: 0, pending: 0, failed: 0, truncated: false, offline: false,
    };
    const all = await this.repository.list();
    const synced = all.filter((capture) => capture.serverCaptureId !== undefined);
    const wanted = synced.slice(0, MAX_PER_RUN);
    outcome.truncated = synced.length > wanted.length;

    let done = 0;
    let consecutiveFailures = 0;
    for (const capture of wanted) {
      try {
        const found = await this.client.analysis(capture.serverCaptureId!);
        const empty = found.calls.length === 0 && (found.waveform ?? []).length === 0;
        if (empty) {
          // Nothing to store yet — the job is queued, or the capture has never
          // been analyzed. Deliberately not written: an empty row would be
          // indistinguishable from "analyzed, found nothing", and the screen
          // says different things about those two.
          outcome.pending += 1;
        } else {
          await this.cache.save(capture.uuid, {
            calls: found.calls,
            waveform: found.waveform ?? [],
            duration: found.duration,
          });
          outcome.stored += 1;
        }
        consecutiveFailures = 0;
      } catch {
        // One capture's analysis failing says nothing about the next one's, and
        // this is a cache warm — there is nothing here worth stopping for.
        outcome.failed += 1;
        consecutiveFailures += 1;
      }
      done += 1;
      onProgress?.(done, wanted.length);
      if (consecutiveFailures >= GIVE_UP_AFTER) {
        outcome.offline = true;
        break;
      }
    }
    return outcome;
  }
}
