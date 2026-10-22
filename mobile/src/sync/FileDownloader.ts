import { Directory, File, Paths } from "expo-file-system";

import type { Downloader } from "./Restore";

/**
 * Streams a URL to a file on the device.
 *
 * Straight to disk rather than through JS: a field recording is tens of
 * megabytes, and holding one in memory to write it out again is a spike on a
 * phone that may also be recording.
 *
 * Restored audio goes to its own directory so it is distinguishable from
 * anything the recorder wrote — a restore is a copy of what the server holds,
 * and the difference is worth being able to see on disk.
 */
export class FileDownloader implements Downloader {
  private readonly dir = new Directory(Paths.document, "restored");

  async download(
    url: string,
    headers: Record<string, string>,
    filename: string,
  ): Promise<{ path: string; bytes: number }> {
    if (!this.dir.exists) this.dir.create({ intermediates: true });
    const target = new File(this.dir, filename);
    // Overwrite rather than resume: restore only ever runs for a capture the
    // phone does not have, so a leftover part-file is debris from a failed
    // attempt and not something to continue.
    if (target.exists) target.delete();

    const downloaded = await File.downloadFileAsync(url, target, { headers });
    return { path: downloaded.uri, bytes: downloaded.size ?? 0 };
  }
}
