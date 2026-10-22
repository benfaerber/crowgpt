/**
 * Making a quiet recording listenable, without lying about it.
 *
 * Field audio sits far below full scale. The recorder runs on UNPROCESSED,
 * which on these phones is ~17 dB below VOICE_RECOGNITION and has no automatic
 * gain at all — deliberately, because AGC pumps the noise floor up between
 * calls and makes one recording incomparable with the next. The consequence is
 * that a crow ten metres up peaks around -30 dBFS, and reviewing it means
 * holding the phone to your ear at full volume.
 *
 * So gain is applied at *playback* only. The stored WAV is never rewritten:
 * it is the thing the analyzer reads, the thing that gets uploaded, and the
 * only copy of what the microphone actually heard. A corpus that has been
 * quietly normalised is one where SNR, absolute level and distance can no
 * longer be measured — and two of those have already decided experiments.
 */

/** Where the loud part of the recording should land. Just under full scale. */
const TARGET_DBFS = -1;

/**
 * Ceiling on the boost. Past this the noise floor arrives before the call
 * does, and 40 dB of hiss is not a review aid.
 */
const MAX_BOOST_DB = 30;

/**
 * The fraction of samples allowed to exceed the target and be clamped.
 *
 * Normalising to the single loudest sample is what makes peak normalisation
 * useless in the field: one car door, one handling knock, and the whole
 * recording stays quiet because a single transient already reaches full scale.
 * Ignoring the top 0.1% steps over the click and normalises the recording
 * rather than its worst moment.
 */
const CLIP_FRACTION = 0.001;

export interface GainPlan {
  /** Multiplier to apply to every sample. 1 means it was already fine. */
  factor: number;
  /** The same as decibels, for saying out loud. Negative means turned down. */
  appliedDb: number;
  /** Level of the recording before the change, for the same reason. */
  peakDbfs: number;
  /** True when the boost hit its ceiling — the recording is quieter than can be fixed. */
  atCeiling: boolean;
}

const FULL_SCALE = 32767;

function toDb(ratio: number): number {
  return ratio <= 0 ? -Infinity : 20 * Math.log10(ratio);
}

/**
 * Work out how much to turn this recording up.
 *
 * Deliberately a plan rather than the audio itself: the decision is worth
 * testing on the host and worth showing on screen — "+18 dB" next to the play
 * button is the difference between a helpful feature and a mysterious one.
 */
export function planGain(samples: Int16Array): GainPlan {
  if (samples.length === 0) {
    return { factor: 1, appliedDb: 0, peakDbfs: -Infinity, atCeiling: false };
  }

  // A histogram rather than a sort: 20 seconds is a million samples, and
  // sorting them to find one percentile costs far more than counting them.
  const buckets = new Int32Array(FULL_SCALE + 2);
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const magnitude = Math.min(Math.abs(samples[index]), FULL_SCALE);
    buckets[magnitude] += 1;
    if (magnitude > peak) peak = magnitude;
  }

  const allowed = Math.floor(samples.length * CLIP_FRACTION);
  let seen = 0;
  let reference = peak;
  for (let level = FULL_SCALE; level >= 0; level -= 1) {
    seen += buckets[level];
    if (seen > allowed) {
      reference = level;
      break;
    }
  }

  const target = FULL_SCALE * Math.pow(10, TARGET_DBFS / 20);
  const wanted = reference > 0 ? target / reference : 1;
  const ceiling = Math.pow(10, MAX_BOOST_DB / 20);
  const factor = Math.min(wanted, ceiling);

  return {
    factor,
    appliedDb: toDb(factor),
    peakDbfs: toDb(peak / FULL_SCALE),
    atCeiling: wanted > ceiling,
  };
}

/**
 * Apply the plan in place, clamping rather than wrapping.
 *
 * Wrapping is the classic way to turn a loud moment into a burst of noise:
 * 32768 as a signed 16-bit integer is -32768, so a clipped peak inverts and
 * what should be a slightly flattened call becomes a crack.
 */
export function applyGain(samples: Int16Array, factor: number): number {
  if (factor === 1) return 0;
  let clamped = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const scaled = Math.round(samples[index] * factor);
    if (scaled > FULL_SCALE) {
      samples[index] = FULL_SCALE;
      clamped += 1;
    } else if (scaled < -FULL_SCALE) {
      samples[index] = -FULL_SCALE;
      clamped += 1;
    } else {
      samples[index] = scaled;
    }
  }
  return clamped;
}

/** "+18 dB", or nothing at all when the change is too small to mention. */
export function describeGain(plan: GainPlan): string | undefined {
  const rounded = Math.round(plan.appliedDb);
  if (rounded === 0) return undefined;
  return `${rounded > 0 ? "+" : ""}${rounded} dB`;
}
