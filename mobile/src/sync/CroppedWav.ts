import type { MediaSource } from "./MediaSource";
import { byteOffsetForSecond, parseWavHeader, type WavFormat } from "./wavEnvelope";

/** A 44-byte canonical PCM WAV header for a payload of `dataBytes`. */
export function buildWavHeader(format: WavFormat, dataBytes: number): Uint8Array {
  const header = new Uint8Array(44);
  const view = new DataView(header.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) header[offset + i] = text.charCodeAt(i);
  };
  const byteRate = (format.sampleRate * format.channels * format.bitsPerSample) / 8;
  const blockAlign = (format.channels * format.bitsPerSample) / 8;

  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, format.channels, true);
  view.setUint32(24, format.sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, format.bitsPerSample, true);
  ascii(36, "data");
  view.setUint32(40, dataBytes, true);
  return header;
}

export interface Crop {
  startSec?: number;
  endSec?: number;
}

/**
 * Presents a cropped span of a WAV as if it were a whole file.
 *
 * Cropping happens at upload time as a *view*, not an edit: the recording on
 * disk is never rewritten, so a mis-dragged handle cannot destroy audio, the
 * crop stays adjustable after the fact, and no second copy of a multi-megabyte
 * file is written to a phone that may be short on space.
 *
 * A fresh 44-byte header is synthesised in front of the selected samples, which
 * also drops any LIST/INFO chunk ffmpeg left in a seeded file.
 */
export class CroppedWavSource implements MediaSource {
  private readonly cache = new Map<string, { format: WavFormat; header: Uint8Array; from: number; to: number }>();

  constructor(
    private readonly inner: MediaSource,
    private readonly cropFor: (path: string) => Crop | undefined,
  ) {}

  private async plan(path: string) {
    const cached = this.cache.get(path);
    if (cached) return cached;

    const format = parseWavHeader(await this.inner.read(path, 0, 4096));
    const crop = this.cropFor(path) ?? {};
    const fileEnd = format.dataOffset + format.dataBytes;

    const from = crop.startSec === undefined
      ? format.dataOffset
      : Math.min(byteOffsetForSecond(format, crop.startSec), fileEnd);
    const to = crop.endSec === undefined
      ? fileEnd
      : Math.min(byteOffsetForSecond(format, crop.endSec), fileEnd);

    const payload = Math.max(0, to - from);
    const plan = { format, header: buildWavHeader(format, payload), from, to: from + payload };
    this.cache.set(path, plan);
    return plan;
  }

  /** Whatever this reports is what sync treats as the whole file. */
  async size(path: string): Promise<number> {
    const { header, from, to } = await this.plan(path);
    return header.byteLength + (to - from);
  }

  async read(path: string, offset: number, length: number): Promise<Uint8Array> {
    const { header, from, to } = await this.plan(path);
    const out = new Uint8Array(Math.max(0, Math.min(length, header.byteLength + (to - from) - offset)));
    if (out.byteLength === 0) return out;

    let written = 0;
    // The synthesised header comes first, then the selected PCM. A chunk can
    // straddle the join, so both halves are filled in one pass.
    if (offset < header.byteLength) {
      const slice = header.subarray(offset, Math.min(header.byteLength, offset + out.byteLength));
      out.set(slice, 0);
      written = slice.byteLength;
    }
    if (written < out.byteLength) {
      const pcmOffset = Math.max(0, offset - header.byteLength);
      const body = await this.inner.read(path, from + pcmOffset, out.byteLength - written);
      out.set(body.subarray(0, out.byteLength - written), written);
    }
    return out;
  }
}
