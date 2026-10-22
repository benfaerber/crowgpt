import type { CaptureRepository } from "../data/CaptureRepository";
import type { DictationRepository } from "../data/DictationRepository";
import type { FieldServerClient } from "../net/FieldServerClient";
import type { ServerDictation } from "../net/serverTypes";
import { log } from "../app/Log";

/**
 * Bring back what the server made of the notes it has.
 *
 * THE EXCEPTION TO PUSH-ONLY, and a narrow one. That rule exists so a stale
 * server copy cannot overwrite a field recording — but a transcript is
 * produced ON the server, from audio the phone already sent, so the phone has
 * no version of it to contradict. `PrefetchAnalysis` pulls the detections for
 * exactly the same reason.
 *
 * RUN FROM THE END OF THE SYNC RUN, NOT FROM THE PUSH. It lived inside
 * `pushDictations` first, which meant it only happened for a capture that had
 * something to send — so a note already uploaded sat at "transcript arrives on
 * the next sync" while every later sync said "Nothing to sync" and did not
 * visit it. Forever, again, one level down from the last time.
 *
 * Additive: fills `transcript` and touches nothing else. Failures are
 * swallowed, because a missing transcript leaves a row that still says sent
 * and failing a sync over one would risk the audio to fetch some text.
 */
export class PullTranscripts {
  constructor(
    private readonly repository: CaptureRepository,
    private readonly dictations: DictationRepository,
    private readonly client: FieldServerClient,
  ) {}

  /** Returns how many transcripts arrived. */
  async run(): Promise<number> {
    const waiting = await this.allWaiting();
    if (waiting.length === 0) return 0;
    // Grouped by capture because that is what the route takes, and one request
    // per capture rather than per note.
    const byCapture = new Map<string, typeof waiting>();
    for (const note of waiting) {
      const list = byCapture.get(note.captureUuid) ?? [];
      list.push(note);
      byCapture.set(note.captureUuid, list);
    }
    // Fetched once per server capture across the whole run, because a merge
    // and its parts can point at the same row up there.
    const listings = new Map<number, ServerDictation[] | null>();
    const listing = async (serverCaptureId: number) => {
      if (!listings.has(serverCaptureId)) {
        try {
          listings.set(serverCaptureId, await this.client.listDictations(serverCaptureId));
        } catch (failure) {
          log.warn("sync", `could not fetch transcripts for server capture ${serverCaptureId}`, failure);
          listings.set(serverCaptureId, null);
        }
      }
      return listings.get(serverCaptureId) ?? null;
    };
    let fetched = 0;
    for (const [captureUuid, notes] of byCapture) {
      const capture = await this.repository.get(captureUuid);
      if (!capture) continue;
      // Both places the note can live on the server. One pushed before a merge
      // sits under the part's own capture; one pushed after sits under the
      // merge's, because that is the id `pushDictations` had in hand.
      const serverCaptureIds = [capture.serverCaptureId];
      if (capture.mergedInto) {
        serverCaptureIds.push(
          (await this.repository.get(capture.mergedInto))?.serverCaptureId);
      }
      const byId = new Map<number, ServerDictation>();
      for (const serverCaptureId of serverCaptureIds) {
        if (serverCaptureId === undefined) continue;
        for (const row of (await listing(serverCaptureId)) ?? []) byId.set(row.id, row);
      }
      for (const note of notes) {
        const transcript = note.serverId ? byId.get(note.serverId)?.transcript : undefined;
        if (!transcript) continue;
        try {
          await this.dictations.update(note.uuid, {
            transcript, transcriptAt: new Date().toISOString(),
          });
          fetched += 1;
        } catch (failure) {
          log.warn("sync", `could not store the transcript for ${note.uuid}`, failure);
        }
      }
    }
    return fetched;
  }

  /** Notes the server has, that this phone has no transcript for yet. */
  private async allWaiting() {
    // The merges' parts as well — `list()` hides them, but `pushDictations`
    // sends their notes, and a note that can go up must be able to get its
    // transcript back down.
    const owners = (await this.repository.list())
      .flatMap((capture) => [capture.uuid, ...(capture.mergedFrom ?? [])]);
    const everything = await this.dictations.forCaptures(owners);
    return everything.filter((note) => note.serverId !== undefined && !note.transcript);
  }
}
