/**
 * Reads a capture's audio off the device in slices.
 *
 * Behind an interface because a resumable upload needs ranged reads, and how
 * you get those differs by platform — while the sync engine that drives them
 * doesn't care. The tests use an in-memory implementation.
 */
export interface MediaSource {
  size(path: string): Promise<number>;
  /** Bytes `[offset, offset + length)`. May return fewer at end of file. */
  read(path: string, offset: number, length: number): Promise<Uint8Array>;
}

/** For tests and for exercising the engine with no device attached. */
export class MemoryMediaSource implements MediaSource {
  private readonly files = new Map<string, Uint8Array>();

  put(path: string, bytes: Uint8Array): void {
    this.files.set(path, bytes);
  }

  async size(path: string): Promise<number> {
    return this.require(path).byteLength;
  }

  async read(path: string, offset: number, length: number): Promise<Uint8Array> {
    const bytes = this.require(path);
    return bytes.subarray(offset, Math.min(offset + length, bytes.byteLength));
  }

  private require(path: string): Uint8Array {
    const bytes = this.files.get(path);
    if (!bytes) throw new Error(`no such file: ${path}`);
    return bytes;
  }
}
