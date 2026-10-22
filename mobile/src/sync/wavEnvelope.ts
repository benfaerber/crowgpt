import type { MediaSource } from "./MediaSource";

export interface WavFormat {
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
  /** Byte offset of the first PCM sample. */
  dataOffset: number;
  /** Length of the PCM payload in bytes. */
  dataBytes: number;
}

export interface WavEnvelope {
  /** Peak amplitude per bucket, 0..1, normalised to the loudest bucket. */
  peaks: number[];
  durationSec: number;
  format: WavFormat;
}

/** Matches the server's envelope resolution so a capture looks the same before and after sync. */
export const ENVELOPE_BUCKETS = 200;

/**
 * Locate the `fmt ` and `data` chunks.
 *
 * Deliberately parses the RIFF chunk list rather than assuming a 44-byte header:
 * our own recorder writes a canonical one, but seeded captures come out of
 * ffmpeg, which inserts a LIST/INFO chunk — reading those bytes as audio makes
 * the first bucket a spike of metadata.
 */
export function parseWavHeader(head: Uint8Array): WavFormat {
  const view = new DataView(head.buffer, head.byteOffset, head.byteLength);
  const tag = (offset: number) => String.fromCharCode(...head.subarray(offset, offset + 4));

  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a RIFF/WAVE file");

  let offset = 12;
  let format: Partial<WavFormat> = {};
  while (offset + 8 <= head.byteLength) {
    const id = tag(offset);
    const size = view.getUint32(offset + 4, true);
    const body = offset + 8;

    if (id === "fmt ") {
      format = {
        ...format,
        channels: view.getUint16(body + 2, true),
        sampleRate: view.getUint32(body + 4, true),
        bitsPerSample: view.getUint16(body + 14, true),
      };
    } else if (id === "data") {
      format = { ...format, dataOffset: body, dataBytes: size };
      break;
    }
    offset = body + size + (size % 2); // chunks are word-aligned
  }

  const { sampleRate, channels, bitsPerSample, dataOffset, dataBytes } = format;
  if (!sampleRate || !channels || !bitsPerSample || dataOffset === undefined || dataBytes === undefined) {
    throw new Error("WAV header missing fmt or data chunk");
  }
  return { sampleRate, channels, bitsPerSample, dataOffset, dataBytes };
}

/** Byte offset of a moment in the file, snapped to a whole frame. */
export function byteOffsetForSecond(format: WavFormat, seconds: number): number {
  const frameBytes = (format.bitsPerSample / 8) * format.channels;
  const frame = Math.max(0, Math.round(seconds * format.sampleRate));
  return format.dataOffset + Math.min(frame * frameBytes, format.dataBytes);
}

/**
 * Peak envelope of a capture, read straight off the phone.
 *
 * The point is to show a waveform *before* the capture has ever been uploaded —
 * until now the trace came back from the server's analysis, so an unsynced
 * recording was a blank rectangle and there was nothing to crop against.
 *
 * Reads in chunks rather than loading the file: a 20-second capture is ~2 MB,
 * but nothing stops a recording running for minutes.
 */
export async function computeWavEnvelope(
  media: MediaSource,
  path: string,
  buckets = ENVELOPE_BUCKETS,
  chunkBytes = 256 * 1024,
): Promise<WavEnvelope> {
  const head = await media.read(path, 0, 4096);
  const format = parseWavHeader(head);
  if (format.bitsPerSample !== 16) {
    throw new Error(`expected 16-bit PCM, got ${format.bitsPerSample}-bit`);
  }

  const total = Math.min(format.dataBytes, (await media.size(path)) - format.dataOffset);
  const frameBytes = 2 * format.channels;
  const totalFrames = Math.floor(total / frameBytes);
  const framesPerBucket = Math.max(1, Math.floor(totalFrames / buckets));

  const peaks = new Array<number>(buckets).fill(0);
  let frame = 0;
  let offset = format.dataOffset;
  const end = format.dataOffset + total;

  while (offset < end) {
    const want = Math.min(chunkBytes, end - offset);
    const chunk = await media.read(path, offset, want);
    if (chunk.byteLength === 0) break;

    // A chunk boundary can land mid-frame; carry the remainder to the next read.
    const usable = chunk.byteLength - (chunk.byteLength % frameBytes);
    const view = new DataView(chunk.buffer, chunk.byteOffset, usable);
    for (let i = 0; i + 1 < usable; i += frameBytes) {
      const sample = Math.abs(view.getInt16(i, true)) / 32768;
      const bucket = Math.min(buckets - 1, Math.floor(frame / framesPerBucket));
      if (sample > peaks[bucket]) peaks[bucket] = sample;
      frame += 1;
    }
    offset += usable;
    if (usable === 0) break;
  }

  const loudest = peaks.reduce((a, b) => Math.max(a, b), 0);
  return {
    peaks: loudest > 0 ? peaks.map((p) => Math.round((p / loudest) * 1000) / 1000) : peaks,
    durationSec: totalFrames / format.sampleRate,
    format,
  };
}
