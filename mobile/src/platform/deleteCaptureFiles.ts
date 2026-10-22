import { File } from "expo-file-system";

/**
 * Delete the media a capture owned.
 *
 * Nothing did this, and for a long time nothing noticed: `remove()` dropped the
 * database row and left the WAV in the cache, so deleting captures leaked disk
 * quietly and forever. What made it visible was orphan recovery — a sweep that
 * treats an unreferenced capture file as an abandoned recording read every one
 * of those leaks as something to restore, and delete stopped working.
 *
 * The marker file is what actually keeps the two apart now (see
 * OrphanCaptures.WRITING_MARKER), so this is no longer load-bearing for that.
 * It is still the right thing: a capture the recordist deleted should not go on
 * occupying a phone that has to hold a day of field audio.
 *
 * Best-effort per file. A capture whose row is gone but whose file could not be
 * removed is untidy; one whose file was removed but whose row survives is a
 * player that spins forever, so the row is deleted last by the caller.
 */
export async function deleteCaptureFiles(
  paths: (string | undefined)[],
  onFailure?: (path: string, failure: unknown) => void,
): Promise<number> {
  let deleted = 0;
  for (const path of paths) {
    if (!path) continue;
    try {
      const file = new File(path);
      // Merged audio that was never materialised, a capture restored on a
      // phone that then lost the file — absence is not a failure here.
      if (!file.exists) continue;
      file.delete();
      deleted += 1;
    } catch (failure) {
      onFailure?.(path, failure);
    }
  }
  return deleted;
}
