import { buildWavHeader } from "./CroppedWav";
import type { MediaSource } from "./MediaSource";
import { parseWavHeader, type WavFormat } from "./wavEnvelope";

/**
 * Presents several recordings as if they were one WAV.
 *
 * A stop-start session is one event held as several captures. Merging joins
 * them — but as a *view*, the same choice CroppedWavSource makes: the parts stay
 * on disk exactly as recorded, and the joined audio is assembled as something
 * reads it. No second copy of a multi-megabyte file on a phone that may be short
 * of space, and a merge that can be undone because nothing was destroyed.
 *
 * The view does not stop at the phone, which is the point. Sync uploads through
 * MediaSource, so what reaches the server is an ordinary WAV — one file, one
 * capture, byte-for-byte what a real concatenation would have produced. The
 * server never learns it was assembled, and training reads a single recording.
 *
 * Byte layout, laid end to end:
 *
 *     [44-byte header][part 0 PCM][silence][part 1 PCM][silence][part 2 PCM]
 *
 * Offsets come from the *files*, not from the durations in the database. Those
 * are metadata and can disagree with what was actually written — a capture cut
 * short by a full disk keeps its intended duration — and an offset that does not
 * match the audio would put every rebased label in the wrong place.
 */

export interface MergeSpec {
  /** Parts in play order. Ordering is decided by planMerge, not here. */
  parts: { uuid: string; audioPath: string }[];
  gapSec: number;
}

export class MergeUnreadable extends Error {}

type Region =
  | { kind: "bytes"; bytes: Uint8Array }
  | { kind: "silence"; length: number }
  | { kind: "part"; uuid: string; path: string; from: number; length: number };

interface Layout {
  format: WavFormat;
  regions: Region[];
  totalBytes: number;
  /** Where each part starts on the merged timeline, measured from the audio. */
  offsets: { uuid: string; offsetMs: number; durationMs: number }[];
}

export class MergedWavSource implements MediaSource {
  private readonly cache = new Map<string, Promise<Layout>>();

  constructor(
    private readonly inner: MediaSource,
    private readonly mergeFor: (path: string) => MergeSpec | undefined,
  ) {}

  /**
   * Where each part landed, in milliseconds, derived from the audio itself.
   *
   * This is what the server's merge record stores. It cannot recompute these —
   * the gap is a client choice — and without them a label made against a part
   * cannot be moved onto the merged timeline or back off it.
   */
  async offsets(path: string) {
    return (await this.layout(path)).offsets;
  }

  async size(path: string): Promise<number> {
    const spec = this.mergeFor(path);
    if (!spec) return this.inner.size(path);
    return (await this.layout(path)).totalBytes;
  }

  async read(path: string, offset: number, length: number): Promise<Uint8Array> {
    const spec = this.mergeFor(path);
    if (!spec) return this.inner.read(path, offset, length);

    const { regions, totalBytes } = await this.layout(path);
    const out = new Uint8Array(Math.max(0, Math.min(length, totalBytes - offset)));
    if (out.byteLength === 0) return out;

    // Walk the regions, copying whatever part of each falls inside the window.
    // A chunked upload lands its boundaries anywhere, so every read has to
    // survive starting or ending mid-region.
    let written = 0;
    let cursor = 0;
    for (const region of regions) {
      if (written >= out.byteLength) break;
      const regionLength = this.lengthOf(region);
      const regionEnd = cursor + regionLength;
      const want = offset + written;

      if (want < regionEnd) {
        const within = want - cursor;
        const take = Math.min(regionLength - within, out.byteLength - written);
        out.set(await this.slice(region, within, take), written);
        written += take;
      }
      cursor = regionEnd;
    }
    return out;
  }

  private lengthOf(region: Region): number {
    if (region.kind === "bytes") return region.bytes.byteLength;
    return region.kind === "silence" ? region.length : region.length;
  }

  private async slice(region: Region, from: number, length: number): Promise<Uint8Array> {
    if (region.kind === "bytes") return region.bytes.subarray(from, from + length);
    // Silence is zeroes; a fresh array already is.
    if (region.kind === "silence") return new Uint8Array(length);
    const body = await this.inner.read(region.path, region.from + from, length);
    // A short read here would silently shift every later part, so it is an
    // error rather than something to pad over.
    if (body.byteLength < length) {
      throw new MergeUnreadable(
        `${region.path} ended early: wanted ${length} bytes at ${region.from + from}, ` +
        `got ${body.byteLength}`);
    }
    return body;
  }

  private layout(path: string): Promise<Layout> {
    const cached = this.cache.get(path);
    if (cached) return cached;
    const built = this.build(path);
    this.cache.set(path, built);
    return built;
  }

  private async build(path: string): Promise<Layout> {
    const spec = this.mergeFor(path)!;
    if (spec.parts.length < 2) {
      throw new MergeUnreadable("a merge needs at least two parts");
    }

    const headers: { uuid: string; path: string; format: WavFormat }[] = [];
    for (const part of spec.parts) {
      headers.push({
        uuid: part.uuid,
        path: part.audioPath,
        format: parseWavHeader(await this.inner.read(part.audioPath, 0, 4096)),
      });
    }

    const first = headers[0].format;
    const clash = headers.find(({ format }) =>
      format.sampleRate !== first.sampleRate
      || format.channels !== first.channels
      || format.bitsPerSample !== first.bitsPerSample);
    if (clash) {
      throw new MergeUnreadable(
        `${clash.path} is ${clash.format.sampleRate} Hz/${clash.format.channels}ch, ` +
        `the merge is ${first.sampleRate} Hz/${first.channels}ch — joining would resample`);
    }

    const frameBytes = (first.bitsPerSample / 8) * first.channels;
    // Snapped to a whole frame: half a frame of silence would shift every
    // following sample into the wrong channel.
    const gapBytes = Math.round(spec.gapSec * first.sampleRate) * frameBytes;
    const msPerByte = 1000 / (first.sampleRate * frameBytes);

    const regions: Region[] = [];
    const offsets: Layout["offsets"] = [];
    let payload = 0;
    headers.forEach(({ uuid, path: partPath, format }, i) => {
      if (i > 0) {
        regions.push({ kind: "silence", length: gapBytes });
        payload += gapBytes;
      }
      offsets.push({
        uuid,
        offsetMs: Math.round(payload * msPerByte),
        durationMs: Math.round(format.dataBytes * msPerByte),
      });
      regions.push({
        kind: "part", uuid, path: partPath,
        from: format.dataOffset, length: format.dataBytes,
      });
      payload += format.dataBytes;
    });

    const header = buildWavHeader(first, payload);
    regions.unshift({ kind: "bytes", bytes: header });

    return {
      format: { ...first, dataOffset: header.byteLength, dataBytes: payload },
      regions,
      totalBytes: header.byteLength + payload,
      offsets,
    };
  }
}
