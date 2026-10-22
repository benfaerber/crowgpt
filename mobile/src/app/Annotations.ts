import type { CaptureRepository } from "../data/CaptureRepository";
import type { ContextRepository } from "../data/ContextRepository";
import type { DictationRepository } from "../data/DictationRepository";
import type { LabelRepository } from "../data/LabelRepository";
import type { ContextRecord } from "../domain/context";
import type { DictationRecord, NewDictation } from "../domain/dictations";
import { DEFAULT_SPECIES, type LabelRecord } from "../domain/labels";
import type { FieldServerClient } from "../net/FieldServerClient";
import { deleteCaptureFiles } from "../platform/deleteCaptureFiles";
import { log } from "./Log";

/**
 * Everything the annotations write against.
 *
 * A required object, not optional positionals — the SyncDeps rule
 * (sync/SyncEngine.ts records the incident). The two functions are functions
 * because their answers move underneath a long-lived object: the client is
 * rebuilt when the app points at a different server, and the config version
 * changes with every vocabulary refresh. Capturing either as a value would
 * quietly pin annotations to a machine or a vocabulary that is gone.
 */
export interface AnnotationDeps {
  repository: CaptureRepository;
  labels: LabelRepository;
  context: ContextRepository;
  dictations: DictationRepository;
  client: () => FieldServerClient;
  configVersion: () => number;
}

/**
 * Make the capture owe the server a push.
 *
 * A label, a context event or a spoken note is not a capture field, so the
 * settings differ cannot notice it — the revision bump is how ground truth
 * added after a sync still makes the trip. See domain/revision.ts.
 */
export async function markCaptureDirty(
  repository: CaptureRepository,
  captureUuid: string,
): Promise<void> {
  const capture = await repository.get(captureUuid);
  if (!capture) return;
  await repository.update(captureUuid, {
    localRevision: (capture.localRevision ?? 0) + 1,
  });
}

/**
 * Ground truth as it is written down: labels, context events, spoken notes.
 *
 * The one shape they share, and the reason they live together: every write
 * here must leave its capture owing the server a push, and every retraction
 * must decide what to do about a copy the server may already hold. The
 * composition root delegates here; the screens keep talking to AppServices.
 */
export class Annotations {
  constructor(private readonly deps: AnnotationDeps) {}

  /**
   * Record what was witnessed, and make the capture owe the server a push.
   *
   * The one thing here that genuinely cannot be recovered later: a recording
   * can be re-listened to and labelled a year from now, but nobody can go back
   * and see whether there was a dog.
   */
  async addContext(input: {
    uuid: string;
    captureUuid: string;
    /** Absent only on a capture confirmed to hold no calls. */
    labelUuid?: string;
    key: string;
    startSec?: number;
    endSec?: number;
  }): Promise<ContextRecord> {
    const event = await this.deps.context.add({
      ...input,
      // What the person was shown. Recorded now because the phone labels
      // offline and syncs later, by which time the cached vocabulary may have
      // moved — and because nothing downstream can reconstruct it.
      configVersion: this.deps.configVersion() || undefined,
      createdAt: new Date().toISOString(),
    });
    await markCaptureDirty(this.deps.repository, input.captureUuid);
    return event;
  }

  async removeContext(event: ContextRecord): Promise<void> {
    if (event.serverId !== undefined) {
      try {
        await this.deps.client().deleteContext(event.serverId);
      } catch {
        // Same trade-off as retracting a label: the local retraction is what
        // was asked for and must not fail for want of signal.
      }
    }
    await this.deps.context.remove(event.uuid);
  }

  /**
   * Record a field label, and make its capture owe the server a push.
   *
   * The bump lives here rather than in the screen that created the label: a
   * label is not a capture field, so the differ cannot notice it, and a screen
   * that forgot to say so would strand ground truth exactly the way a post-sync
   * description used to be stranded.
   */
  async addLabel(input: {
    uuid: string;
    captureUuid: string;
    callType: string;
    startSec: number;
    endSec: number;
    fromDetection?: boolean;
  }): Promise<LabelRecord> {
    const label = await this.deps.labels.add({
      ...input,
      species: DEFAULT_SPECIES,
      // The vocabulary on screen at the moment of the decision — see
      // domain/labels.ts. Zero means the phone has never fetched one, which is
      // not a version and should not be recorded as one.
      configVersion: this.deps.configVersion() || undefined,
      createdAt: new Date().toISOString(),
    });
    // A marked call contradicts "no calls in this one", so the claim goes. The
    // server does the same on its side; doing it here too keeps the phone from
    // showing a silence mark it is about to lose, and from re-asserting it on
    // the next push.
    const capture = await this.deps.repository.get(input.captureUuid);
    if (capture?.silentConfirmedAt !== undefined) {
      await this.deps.repository.update(input.captureUuid, {
        silentConfirmedAt: undefined,
      });
    }
    await markCaptureDirty(this.deps.repository, input.captureUuid);
    return label;
  }

  /**
   * Set (or clear) which bird was watched making a call.
   *
   * Local write first, then the server if it already holds this label — because
   * `pushLabels` skips anything already pushed, so a caller added after a sync
   * would never make the trip otherwise. Offline, the local write stands and
   * the caller travels with the label on its first push.
   *
   * The one field on a label that cannot be recovered later: experiment 0017
   * showed the audio does not carry the caller, so it is seen live or lost.
   * Which is why the network failure below is swallowed rather than surfaced —
   * refusing the tap would lose the answer to protect a round trip.
   */
  async setLabelCaller(label: LabelRecord, callerRole?: string): Promise<LabelRecord> {
    const updated = await this.deps.labels.update(label.uuid, { callerRole });
    if (label.serverId !== undefined) {
      try {
        await this.deps.client().setLabelCaller(label.serverId, callerRole);
      } catch (failure) {
        log.warn("label", "could not publish caller; it stays on the phone", failure);
      }
    }
    return updated;
  }

  /**
   * Retract a label.
   *
   * Ground truth that cannot be taken back is worse than none — a labeller who
   * realises they marked the wrong span would otherwise leave it there, and it
   * enters the training manifest as fact.
   */
  async removeLabel(label: LabelRecord): Promise<void> {
    if (label.serverId !== undefined) {
      // Best effort: offline, the server keeps a label this phone has dropped.
      // Reconciling that needs tombstones, which is its own piece of work.
      try {
        await this.deps.client().deleteLabel(label.serverId);
      } catch {
        // Swallowed deliberately — the local retraction is what the user asked
        // for and must not fail because there is no signal.
      }
    }
    // The server cascades context off a deleted label; do the same locally, or
    // a situation survives attached to a call nobody stands behind any more.
    for (const event of await this.deps.context.forLabel(label.uuid)) {
      await this.removeContext(event);
    }
    await this.deps.labels.remove(label.uuid);
  }

  /**
   * Enter a spoken note against a capture.
   *
   * The row is written before the first byte reaches the file, which is what
   * makes an interrupted memo recognisable afterwards — and what keeps its path
   * out of the orphan sweep's reach in the window before the audio exists.
   */
  async addDictation(dictation: NewDictation): Promise<DictationRecord> {
    const stored = await this.deps.dictations.add(dictation);
    // The capture may already have synced, and `pendingSync` only selects rows
    // that are local, failed, or edited — so without this a note added to a
    // capture that has already gone up would never be pushed, silently and
    // permanently. Same mechanism `addLabel` uses for the same reason.
    await markCaptureDirty(this.deps.repository, dictation.captureUuid);
    return stored;
  }

  /**
   * Forget a note and delete its audio.
   *
   * No server-side retraction: one already sent stays there, and the caller
   * says so rather than pretending. That is the stance `removeLabel` takes —
   * tombstones are their own piece of work and half of one is worse than none.
   */
  async deleteDictation(uuid: string): Promise<void> {
    const found = await this.deps.dictations.get(uuid);
    if (!found) return;
    await deleteCaptureFiles(
      [found.audioPath],
      (path, failure) => log.warn("dictation", `could not delete ${path}`, failure));
    await this.deps.dictations.remove(uuid);
  }

  /**
   * Mark every note the process died in the middle of.
   *
   * The recovery itself is deliberately not attempted: a capture is
   * unrepeatable and gets `recoverOrphans`, but a memo interrupted by a crash
   * can be re-spoken in the next thirty seconds because the recordist is
   * standing right there — PROVIDED he is told it was lost. So what matters is
   * not salvage, it is that the card says so instead of the note quietly not
   * existing.
   *
   * Never throws: a phone that cannot reconcile must still record.
   */
  async reconcileDictations(): Promise<number> {
    try {
      const stale = await this.deps.dictations.stale();
      for (const note of stale) {
        await this.deps.dictations.update(note.uuid, { state: "interrupted" });
        log.warn("dictation", "a spoken note was interrupted by the app stopping", {
          uuid: note.uuid, captureUuid: note.captureUuid,
        });
      }
      return stale.length;
    } catch (failure) {
      log.error("dictation", "could not reconcile spoken notes", failure);
      return 0;
    }
  }
}
