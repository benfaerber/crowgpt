import type { CaptureRepository } from "../data/CaptureRepository";
import { MERGE_GAP_SEC, planMerge, type MergePart } from "./merge";
import type { CaptureRecord } from "./types";

/**
 * Performing a merge: one new capture, and the parts folded into it.
 *
 * Kept apart from the screen that triggers it and from the sync engine that
 * uploads it, because the ordering below is the whole correctness of the
 * feature and it should be testable without either.
 *
 * The merged capture inherits everything from the earliest part — GPS, name,
 * notes, counts, the lot — on the grounds that the recordist described the
 * event once and the first recording is where they described it. It does not
 * inherit sync state: it has never been uploaded, whatever its parts had done.
 */

/** Fields that describe the *event*, and so move to the merged capture. */
const INHERITED = [
  "name", "notes", "description", "keep", "familyUuid",
  "latitude", "longitude", "locationName", "region",
  "observerRole", "distanceBand", "behaviorGuess",
  "adultCount", "juvenileCount", "unagedCount",
] as const;

export interface MergeResult {
  merged: CaptureRecord;
  parts: CaptureRecord[];
  /** Parts that had already reached the server, for the merge record. */
  syncedParts: CaptureRecord[];
}

export interface MergeIds {
  captureUuid: string;
  mediaUuid: string;
}

export class MergeFailed extends Error {}

/**
 * Fold `uuids` into one new capture.
 *
 * Order of writes matters and is deliberate: the merged capture is created and
 * fully described *before* any part is marked as folded away. A crash midway
 * then leaves the parts still listed and an extra capture beside them — untidy,
 * and every recording still reachable. The other order would hide the parts
 * first and lose them all if the insert failed.
 */
export async function mergeCaptures(
  repository: CaptureRepository,
  uuids: string[],
  ids: MergeIds,
  gapSec: number = MERGE_GAP_SEC,
): Promise<MergeResult> {
  const loaded = await Promise.all(uuids.map((uuid) => repository.get(uuid)));
  const missing = uuids.filter((_, i) => loaded[i] === null);
  if (missing.length > 0) {
    throw new MergeFailed(`no such capture: ${missing.join(", ")}`);
  }
  const parts = loaded as CaptureRecord[];

  const alreadyMerged = parts.filter((p) => p.mergedInto !== undefined);
  if (alreadyMerged.length > 0) {
    throw new MergeFailed(
      `already part of a merge: ${alreadyMerged.map((p) => p.uuid).join(", ")}`);
  }
  // Merging a merge would need its parts re-pointed and its offsets rebuilt,
  // and there is no reason to reach for it — un-merge and merge again instead.
  const nested = parts.filter((p) => p.mergedFrom !== undefined);
  if (nested.length > 0) {
    throw new MergeFailed(
      `${nested.map((p) => p.uuid).join(", ")} is itself a merge — un-merge it first`);
  }

  // planMerge owns the ordering and the format refusals; this throws through it
  // rather than duplicating either.
  const plan = planMerge(parts.map((p): MergePart => ({
    uuid: p.uuid,
    recordedAt: p.recordedAt,
    durationMs: p.durationMs,
    sampleRate: p.sampleRate,
    channels: p.channels,
    audioPath: p.audioPath,
  })), gapSec);

  const ordered = plan.parts.map(
    (placed) => parts.find((p) => p.uuid === placed.uuid)!);
  const source = ordered[0];

  const merged = await repository.add({
    uuid: ids.captureUuid,
    mediaUuid: ids.mediaUuid,
    // The event began when its first recording did.
    recordedAt: source.recordedAt,
    durationMs: plan.totalMs,
    sampleRate: source.sampleRate,
    channels: source.channels,
    // Nothing on disk answers to this. MergedWavSource is what makes it
    // readable, and a plain file source failing loudly on it is the correct
    // behaviour if the merge is ever missing from the map.
    audioPath: mergedAudioPath(ids.captureUuid),
    bytes: 0,
  });

  const inherited: Partial<CaptureRecord> = { mergedFrom: ordered.map((p) => p.uuid) };
  for (const field of INHERITED) {
    const value = source[field];
    if (value !== undefined) (inherited as Record<string, unknown>)[field] = value;
  }
  const described = await repository.update(merged.uuid, inherited);

  // Only now are the parts hidden. Until this line every recording is still
  // listed, so a failure above costs nothing but a stray row.
  for (const part of ordered) {
    await repository.update(part.uuid, { mergedInto: merged.uuid });
  }

  return {
    merged: described,
    parts: ordered,
    syncedParts: ordered.filter((p) => p.serverCaptureId !== undefined),
  };
}

/** The synthetic path a merged capture's audio answers to. */
export function mergedAudioPath(uuid: string): string {
  return `merged:${uuid}`;
}

/**
 * Every merge on the device, ready for the upload path.
 *
 * Read from the database at startup rather than remembered from the moment the
 * merge was made. Crops get away with a map the detail screen fills, because a
 * missing entry only means the upload is uncropped. A missing merge means the
 * capture has no audio at all — `merged:<uuid>` is not a file — so an app
 * restarted between merging and syncing would fail to upload and could not
 * explain why. What the database knows has to be enough.
 */
export async function loadMergeSpecs(
  repository: CaptureRepository,
  gapSec: number = MERGE_GAP_SEC,
): Promise<Map<string, { parts: { uuid: string; audioPath: string }[]; gapSec: number }>> {
  const specs = new Map<string, { parts: { uuid: string; audioPath: string }[]; gapSec: number }>();
  for (const capture of await repository.list()) {
    if (!capture.mergedFrom) continue;
    const parts: { uuid: string; audioPath: string }[] = [];
    for (const uuid of capture.mergedFrom) {
      const part = await repository.get(uuid);
      if (part) parts.push({ uuid: part.uuid, audioPath: part.audioPath });
    }
    // A merge missing a part would silently upload shorter audio than the
    // capture claims, so it is left out and fails loudly at read instead.
    if (parts.length === capture.mergedFrom.length) {
      specs.set(capture.audioPath, { parts, gapSec });
    }
  }
  return specs;
}

export function isMergedAudioPath(path: string): boolean {
  return path.startsWith("merged:");
}

/**
 * Bring a merge apart again.
 *
 * The parts are all still there, so this is only a matter of forgetting: clear
 * the pointers, drop the row that held them together. `remove` releases the
 * parts as well, so the order here is belt and braces rather than load-bearing.
 */
export async function unmergeCapture(
  repository: CaptureRepository,
  mergedUuid: string,
): Promise<CaptureRecord[]> {
  const merged = await repository.get(mergedUuid);
  if (!merged) throw new MergeFailed(`no such capture: ${mergedUuid}`);
  if (!merged.mergedFrom) throw new MergeFailed(`${mergedUuid} is not a merge`);

  const restored: CaptureRecord[] = [];
  for (const uuid of merged.mergedFrom) {
    const part = await repository.get(uuid);
    if (part) restored.push(await repository.update(uuid, { mergedInto: undefined }));
  }
  await repository.remove(mergedUuid);
  return restored;
}

/**
 * Give any merge that has no file behind it one.
 *
 * Merges made by the first build of this feature carry `merged:<uuid>` as their
 * audio path, which is not a file: their player never finished loading and
 * their size read zero. The audio was never lost — the parts are untouched, and
 * one that had synced is whole on the server — so repairing is a matter of
 * writing out what was always derivable.
 *
 * Runs at startup, once, and returns how many it fixed. A failure on one is
 * logged by the caller and does not stop the rest: the alternative is a phone
 * that will not open because an old capture cannot be rebuilt.
 */
export async function repairUnmaterialisedMerges(
  repository: CaptureRepository,
  write: (uuid: string, parts: { uuid: string; audioPath: string }[])
    => Promise<{ path: string; bytes: number }>,
  onFailure: (uuid: string, failure: unknown) => void,
): Promise<number> {
  let repaired = 0;
  for (const capture of await repository.list()) {
    if (!capture.mergedFrom || !isMergedAudioPath(capture.audioPath)) continue;
    try {
      const parts: { uuid: string; audioPath: string }[] = [];
      for (const uuid of capture.mergedFrom) {
        const part = await repository.get(uuid);
        if (part) parts.push({ uuid: part.uuid, audioPath: part.audioPath });
      }
      if (parts.length !== capture.mergedFrom.length) {
        throw new MergeFailed(`${capture.uuid} is missing parts on disk`);
      }
      const audio = await write(capture.uuid, parts);
      await repository.update(capture.uuid, {
        audioPath: audio.path,
        bytes: audio.bytes,
      });
      repaired += 1;
    } catch (failure) {
      onFailure(capture.uuid, failure);
    }
  }
  return repaired;
}
