import type { LogRepository } from "../data/LogRepository";
import type { FieldServerClient } from "../net/FieldServerClient";

/** One request. Large enough that a bad afternoon is a handful of round trips. */
const BATCH = 200;
/** A ceiling per run, so a backlog cannot turn a capture sync into a log upload. */
const MAX_BATCHES = 10;

export interface LogSyncOutcome {
  sent: number;
  /** Set when the push failed. The lines stay pending; nothing is lost. */
  error?: string;
}

/**
 * Send the phone's log to the server.
 *
 * Separate from SyncEngine, and deliberately so. Sync is about the corpus:
 * captures, labels, the things that cannot be recreated. Logs are about the
 * app, they are disposable, and they must never be able to fail a run that
 * carried a field recording — a diagnostic upload that turns a successful sync
 * into a failed one has inverted its own purpose.
 *
 * So this returns its failure rather than throwing it, and lines are marked
 * sent only once the server names them. A dropped response means the batch
 * comes again, which the server's idempotency key makes free.
 */
export class LogSync {
  constructor(
    private readonly logs: LogRepository,
    private readonly client: FieldServerClient,
  ) {}

  async run(): Promise<LogSyncOutcome> {
    let sent = 0;
    for (let batch = 0; batch < MAX_BATCHES; batch += 1) {
      const pending = await this.logs.pendingSync(BATCH);
      if (pending.length === 0) break;
      try {
        const answer = await this.client.pushLogs(
          pending.map((entry) => ({
            clientUuid: entry.uuid,
            at: entry.at,
            level: entry.level,
            tag: entry.tag,
            message: entry.message,
            detail: entry.detail,
          })),
        );
        sent += answer.accepted.length;
        // The whole batch is marked, not just what came back accepted. The
        // server takes every line it can parse and refuses only one that cannot
        // be deduplicated — which it will refuse identically forever. Marking
        // only the accepted ones leaves the rest at the head of the queue, and
        // every later run re-sends them, re-marks the same accepted lines and
        // never advances. A log line is not worth a queue that cannot drain.
        await this.logs.markSynced(pending.map((entry) => entry.uuid));
      } catch (failure) {
        return {
          sent,
          error: failure instanceof Error ? failure.message : String(failure),
        };
      }
    }
    return { sent };
  }
}
