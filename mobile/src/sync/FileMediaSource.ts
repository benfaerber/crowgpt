import { File } from "expo-file-system";

import type { MediaSource } from "./MediaSource";

/**
 * Reads capture audio off the device in slices.
 *
 * Deliberately uses a seekable handle rather than reading the file whole: a
 * long field recording is tens of megabytes, and pulling all of it into JS just
 * to send one 256 KiB chunk would be a memory spike per chunk on a phone that
 * may also be recording.
 */
export class FileMediaSource implements MediaSource {
  async size(path: string): Promise<number> {
    return new File(this.uri(path)).size;
  }

  async read(path: string, offset: number, length: number): Promise<Uint8Array> {
    const handle = new File(this.uri(path)).open();
    try {
      handle.offset = offset;
      return handle.readBytes(length);
    } finally {
      handle.close();
    }
  }

  /** The native module wants a URI; `raw-audio` hands back a bare absolute path. */
  private uri(path: string): string {
    return path.startsWith("file://") ? path : `file://${path}`;
  }
}
