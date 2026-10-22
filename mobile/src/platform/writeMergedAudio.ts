import { Directory, File, Paths } from "expo-file-system";

import { MERGE_GAP_SEC } from "../domain/merge";
import { FileMediaSource } from "../sync/FileMediaSource";
import { MergedWavSource } from "../sync/MergedWav";

/**
 * Write a merged capture's audio to a real file on disk.
 *
 * The first version of this assembled the joined audio on read and never wrote
 * it, so the parts stayed the only copy and a merge cost no space. That was
 * right for the upload path — sync goes through MediaSource, so the server
 * received an ordinary WAV either way — and wrong for everything else in the
 * app. Playback, the waveform envelope and the normaliser all take a `file://`
 * URI and hand it to the OS, so a capture whose path was `merged:<uuid>` showed
 * a player that never finished loading and a size of zero bytes.
 *
 * Materialising costs a second copy of the audio, which the view was avoiding.
 * The property that actually mattered survives untouched: the parts are still
 * on disk exactly as recorded, so un-merging remains a matter of forgetting and
 * a mis-tapped selection still cannot destroy a recording.
 */
export async function writeMergedAudio(
  uuid: string,
  parts: { uuid: string; audioPath: string }[],
  gapSec: number = MERGE_GAP_SEC,
): Promise<{ path: string; bytes: number }> {
  // Beside the recordings rather than in the cache: the OS may empty the cache
  // whenever it likes, and this is a capture, not a derived convenience.
  const directory = new Directory(Paths.document, "merged");
  if (!directory.exists) directory.create({ intermediates: true });

  const key = `merged:${uuid}`;
  const source = new MergedWavSource(
    new FileMediaSource(),
    (path) => (path === key ? { parts, gapSec } : undefined),
  );

  const size = await source.size(key);
  const bytes = await source.read(key, 0, size);
  if (bytes.byteLength !== size) {
    throw new Error(
      `merged audio came back short: ${bytes.byteLength} of ${size} bytes`);
  }

  const target = new File(directory, `${uuid}.wav`);
  if (target.exists) target.delete();
  target.create();
  target.write(bytes);
  return { path: target.uri, bytes: size };
}

/** Remove a merged capture's assembled audio. The parts are not touched. */
export function deleteMergedAudio(uuid: string): void {
  const target = new File(new Directory(Paths.document, "merged"), `${uuid}.wav`);
  if (target.exists) target.delete();
}
