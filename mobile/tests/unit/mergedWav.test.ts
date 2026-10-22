import { describe, expect, it } from "vitest";

import { buildWavHeader } from "../../src/sync/CroppedWav";
import { MemoryMediaSource } from "../../src/sync/MediaSource";
import { MergeUnreadable, MergedWavSource, type MergeSpec } from "../../src/sync/MergedWav";
import { parseWavHeader } from "../../src/sync/wavEnvelope";

const RATE = 48000;
const FRAME = 2; // 16-bit mono

/** A WAV whose every sample is `value`, so a byte says which part it came from. */
function wav(seconds: number, value: number, rate = RATE, channels = 1): Uint8Array {
  const frames = Math.round(seconds * rate);
  const dataBytes = frames * (channels * 2);
  const header = buildWavHeader(
    { sampleRate: rate, channels, bitsPerSample: 16, dataOffset: 44, dataBytes },
    dataBytes);
  const out = new Uint8Array(header.byteLength + dataBytes);
  out.set(header, 0);
  const view = new DataView(out.buffer, header.byteLength, dataBytes);
  for (let i = 0; i < dataBytes / 2; i += 1) view.setInt16(i * 2, value, true);
  return out;
}

function fixture(gapSec = 3, files: [string, Uint8Array][] = [
  ["/a.wav", wav(1, 100)],
  ["/b.wav", wav(2, 200)],
  ["/c.wav", wav(0.5, 300)],
]) {
  const inner = new MemoryMediaSource();
  for (const [path, bytes] of files) inner.put(path, bytes);
  const spec: MergeSpec = {
    parts: files.map(([path], i) => ({ uuid: `p${i}`, audioPath: path })),
    gapSec,
  };
  const source = new MergedWavSource(inner, (p) => (p === "/merged" ? spec : undefined));
  return { inner, source };
}

async function readAll(source: MergedWavSource, path: string): Promise<Uint8Array> {
  const total = await source.size(path);
  return source.read(path, 0, total);
}

describe("the file it presents", () => {
  it("is a valid WAV", async () => {
    const { source } = fixture();
    const format = parseWavHeader(await readAll(source, "/merged"));
    expect(format.sampleRate).toBe(RATE);
    expect(format.channels).toBe(1);
  });

  it("is as long as the parts plus the gaps", async () => {
    const { source } = fixture(3);
    // 1s + 3s gap + 2s + 3s gap + 0.5s = 9.5s
    const expected = 44 + Math.round(9.5 * RATE) * FRAME;
    expect(await source.size("/merged")).toBe(expected);
  });

  it("declares its payload honestly in the header", async () => {
    const { source } = fixture();
    const all = await readAll(source, "/merged");
    const format = parseWavHeader(all);
    expect(format.dataBytes).toBe(all.byteLength - 44);
  });

  it("passes a path that is not a merge straight through", async () => {
    const { inner, source } = fixture();
    inner.put("/plain.wav", wav(1, 7));
    expect(await source.size("/plain.wav")).toBe(await inner.size("/plain.wav"));
  });
});

describe("what the audio actually contains", () => {
  const sampleAt = (all: Uint8Array, seconds: number) =>
    new DataView(all.buffer, all.byteOffset, all.byteLength)
      .getInt16(44 + Math.round(seconds * RATE) * FRAME, true);

  it("plays the parts in order", async () => {
    const { source } = fixture(3);
    const all = await readAll(source, "/merged");
    expect(sampleAt(all, 0.5)).toBe(100);      // part a
    expect(sampleAt(all, 5)).toBe(200);        // part b, after 1s + 3s gap
    expect(sampleAt(all, 9.2)).toBe(300);      // part c
  });

  it("puts silence between them", async () => {
    const { source } = fixture(3);
    const all = await readAll(source, "/merged");
    expect(sampleAt(all, 2.5)).toBe(0);
    expect(sampleAt(all, 6.5)).toBe(0);
  });

  it("does not leave a gap after the last part", async () => {
    const { source } = fixture(3);
    const all = await readAll(source, "/merged");
    expect(sampleAt(all, 9.49)).toBe(300);
  });

  it("never rewrites the files on disk", async () => {
    const { inner, source } = fixture();
    const before = await inner.read("/a.wav", 0, 1_000_000);
    await readAll(source, "/merged");
    expect(await inner.read("/a.wav", 0, 1_000_000)).toEqual(before);
  });
});

describe("chunked reads, as sync makes them", () => {
  it("match a single read", async () => {
    const { source } = fixture();
    const whole = await readAll(source, "/merged");
    const chunked = new Uint8Array(whole.byteLength);
    for (let offset = 0; offset < whole.byteLength; offset += 7919) {
      const chunk = await source.read("/merged", offset, 7919);
      chunked.set(chunk, offset);
    }
    expect(chunked).toEqual(whole);
  });

  it("survive a boundary landing inside the header", async () => {
    const { source } = fixture();
    const whole = await readAll(source, "/merged");
    const head = await source.read("/merged", 0, 20);
    const rest = await source.read("/merged", 20, 60);
    expect([...head, ...rest]).toEqual([...whole.subarray(0, 80)]);
  });

  it("survive a boundary landing inside a silence", async () => {
    const { source } = fixture(3);
    const at = 44 + Math.round(2 * RATE) * FRAME;   // 1s into the first gap
    const whole = await readAll(source, "/merged");
    const chunk = await source.read("/merged", at, 100);
    expect(chunk).toEqual(whole.subarray(at, at + 100));
  });

  it("clamp a read that runs past the end", async () => {
    const { source } = fixture();
    const total = await source.size("/merged");
    expect((await source.read("/merged", total - 10, 500)).byteLength).toBe(10);
  });
});

describe("the offsets the server is told", () => {
  it("come from the audio, in play order", async () => {
    const { source } = fixture(3);
    expect(await source.offsets("/merged")).toEqual([
      { uuid: "p0", offsetMs: 0, durationMs: 1000 },
      { uuid: "p1", offsetMs: 4000, durationMs: 2000 },
      { uuid: "p2", offsetMs: 9000, durationMs: 500 },
    ]);
  });

  it("track a shorter gap", async () => {
    const { source } = fixture(0);
    const offsets = await source.offsets("/merged");
    expect(offsets.map((o) => o.offsetMs)).toEqual([0, 1000, 3000]);
  });
});

describe("refusing", () => {
  it("will not resample", async () => {
    const { source } = fixture(3, [["/a.wav", wav(1, 100)],
                                   ["/b.wav", wav(1, 200, 44100)]]);
    await expect(readAll(source, "/merged")).rejects.toThrow(/resample/);
  });

  it("will not mix mono and stereo", async () => {
    const { source } = fixture(3, [["/a.wav", wav(1, 100)],
                                   ["/b.wav", wav(1, 200, RATE, 2)]]);
    await expect(readAll(source, "/merged")).rejects.toThrow(MergeUnreadable);
  });

  it("refuses a truncated part rather than shifting everything after it", async () => {
    const inner = new MemoryMediaSource();
    const short = wav(1, 100);
    // A header claiming a second of audio, with half of it missing — a capture
    // cut short by a full disk looks exactly like this.
    inner.put("/a.wav", short.subarray(0, 44 + (short.byteLength - 44) / 2));
    inner.put("/b.wav", wav(1, 200));
    const source = new MergedWavSource(inner, () => ({
      parts: [{ uuid: "p0", audioPath: "/a.wav" }, { uuid: "p1", audioPath: "/b.wav" }],
      gapSec: 1,
    }));
    await expect(readAll(source, "/merged")).rejects.toThrow(/ended early/);
  });
});
