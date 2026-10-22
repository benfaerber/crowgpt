import { Directory, File, Paths } from "expo-file-system";

import { log } from "../app/Log";
import { applyGain, planGain, type GainPlan } from "../domain/gain";
import { parseWavHeader } from "../sync/wavEnvelope";

export interface Normalized {
  /** What to hand the player. The original when nothing was worth changing. */
  uri: string;
  plan: GainPlan;
  /** True when this is the untouched recording. */
  original: boolean;
}

/**
 * Anything longer than this is left alone.
 *
 * The whole file is read into JavaScript to be scaled, so this is a memory
 * ceiling rather than a judgement about length: three minutes of 48 kHz mono is
 * ~17 MB, and a phone that may be recording at the same time should not be
 * asked for more. Long captures are reviewed at a desk anyway.
 */
const MAX_BYTES = 24 * 1024 * 1024;

/**
 * A louder copy of a capture, for listening to.
 *
 * Written to the cache directory, never over the recording. The stored WAV is
 * what the analyzer reads, what gets uploaded, and the only record of what the
 * microphone actually heard — a corpus that has been quietly normalised is one
 * where SNR, absolute level and distance can no longer be measured, and two of
 * those have already decided experiments here.
 *
 * The cache directory is the right home for the copy: the OS may evict it
 * whenever it likes, and the answer to losing one is to make it again.
 */
export class NormalizedWav {
  private readonly done = new Map<string, Normalized>();

  async of(audioPath: string): Promise<Normalized> {
    const source = audioPath.startsWith("file://") ? audioPath : `file://${audioPath}`;
    const held = this.done.get(source);
    // Re-checked rather than trusted: the cache directory is the OS's to empty.
    if (held && (held.original || new File(held.uri).exists)) return held;

    // Then the copy from a previous launch. Only an in-memory map remembered
    // these, so every capture was read, analysed and rewritten again on the
    // first open after every start — work already done, sitting on the disk.
    const onDisk = this.cached(source);
    if (onDisk) {
      this.done.set(source, onDisk);
      return onDisk;
    }

    const result = await this.build(source);
    this.done.set(source, result);
    return result;
  }

  /**
   * A copy made earlier, if one is still there.
   *
   * The gain is in the filename rather than in a sidecar or a database: it is
   * one number, it is already computed, and a cache that has to be read out of
   * two places to be usable is a cache that will disagree with itself.
   */
  private cached(source: string): Normalized | undefined {
    const directory = new Directory(Paths.cache, "normalized");
    if (!directory.exists) return undefined;
    const prefix = `${hash(source)}@`;
    for (const entry of directory.list()) {
      const name = entry.name ?? "";
      if (!name.startsWith(prefix) || !name.endsWith(".wav")) continue;
      const db = Number(name.slice(prefix.length, -4));
      if (!Number.isFinite(db)) continue;
      return {
        uri: entry.uri,
        plan: { factor: Math.pow(10, db / 20), appliedDb: db, peakDbfs: 0, atCeiling: false },
        original: false,
      };
    }
    return undefined;
  }

  private async build(source: string): Promise<Normalized> {
    const startedAt = Date.now();
    const untouched = (plan: GainPlan): Normalized => ({ uri: source, plan, original: true });
    const quiet: GainPlan = { factor: 1, appliedDb: 0, peakDbfs: 0, atCeiling: false };

    const file = new File(source);
    if (!file.exists || file.size === null || file.size > MAX_BYTES) return untouched(quiet);

    const bytes = await file.bytes();
    const format = parseWavHeader(bytes.subarray(0, Math.min(bytes.length, 4096)));
    // 16-bit PCM is what the recorder writes and what the seeder converts to.
    // Anything else is left alone rather than guessed at.
    if (format.bitsPerSample !== 16) return untouched(quiet);

    const samples = new Int16Array(
      bytes.buffer,
      bytes.byteOffset + format.dataOffset,
      Math.floor(Math.min(format.dataBytes, bytes.length - format.dataOffset) / 2),
    );
    const plan = planGain(samples);
    // Under a decibel is not worth a second copy of the audio on the phone.
    if (Math.abs(plan.appliedDb) < 1) return untouched(plan);

    applyGain(samples, plan.factor);

    const directory = new Directory(Paths.cache, "normalized");
    if (!directory.exists) directory.create({ intermediates: true });
    // The gain goes in the name so a later launch can read it back without
    // touching a sample.
    const target = new File(directory, `${hash(source)}@${plan.appliedDb.toFixed(1)}.wav`);
    if (target.exists) target.delete();
    target.create();
    target.write(bytes);

    const took = Date.now() - startedAt;
    // Reading a multi-megabyte file, walking every sample and writing it back
    // happens on the JS thread. Measured at ~200 ms for a thirty-second capture
    // and it should stay there; if it ever does not, this line is the only
    // thing that will say so from a phone in somebody's pocket.
    if (took > 1500) {
      log.warn("playback", "normalising was slow", {
        ms: took,
        samples: samples.length,
        bytes: bytes.length,
      });
    }
    return { uri: target.uri, plan, original: false };
  }
}

/**
 * A stable filename per source path.
 *
 * Not a security hash and not trying to be — it only has to keep two captures
 * from colliding, and to produce the same name next time so the copy can be
 * reused within a session.
 */
function hash(text: string): string {
  let value = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return (value >>> 0).toString(16);
}
