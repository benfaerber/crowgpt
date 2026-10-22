import { describe, expect, it } from "vitest";

import { applyGain, describeGain, planGain } from "../../src/domain/gain";

const FULL_SCALE = 32767;

/** A steady tone at the given fraction of full scale. */
function tone(peakFraction: number, samples = 48_000): Int16Array {
  const out = new Int16Array(samples);
  for (let index = 0; index < samples; index += 1) {
    out[index] = Math.round(
      Math.sin((index / 48_000) * 2 * Math.PI * 1000) * FULL_SCALE * peakFraction,
    );
  }
  return out;
}

/**
 * Turning a field recording up for review.
 *
 * The stored file is never touched — see domain/gain.ts. These are about the
 * decision: how much, and when to refuse.
 */
describe("planning the gain", () => {
  it("brings a quiet recording up near full scale", () => {
    // A crow ten metres up peaks around -30 dBFS, which is why reviewing means
    // holding the phone against your ear.
    const plan = planGain(tone(0.03));
    expect(plan.appliedDb).toBeGreaterThan(20);
    expect(plan.peakDbfs).toBeLessThan(-25);
  });

  it("leaves a recording that is already loud alone", () => {
    const plan = planGain(tone(0.89));
    expect(Math.abs(plan.appliedDb)).toBeLessThan(1);
  });

  it("turns down a recording that is too hot", () => {
    // Normalising is not only a boost: a close capture that sits at full scale
    // is as awkward to review as a distant one.
    expect(planGain(tone(1)).appliedDb).toBeLessThan(0);
  });

  it("refuses to boost past the point where only noise arrives", () => {
    const plan = planGain(tone(0.0001));
    expect(plan.appliedDb).toBeLessThanOrEqual(30);
    expect(plan.atCeiling).toBe(true);
  });

  it("steps over a single transient instead of normalising to it", () => {
    // The reason peak normalisation is useless in the field: one car door, one
    // knock against the phone, and the whole recording stays quiet because that
    // one sample already reaches full scale.
    const samples = tone(0.03);
    samples[500] = FULL_SCALE;
    samples[501] = -FULL_SCALE;

    const plan = planGain(samples);

    expect(plan.appliedDb).toBeGreaterThan(20);
  });

  it("says nothing about an empty file rather than dividing by it", () => {
    expect(planGain(new Int16Array(0)).factor).toBe(1);
  });
});

describe("applying it", () => {
  it("clamps rather than wraps", () => {
    // 32768 as a signed 16-bit integer is -32768: a clipped peak inverts, and
    // a slightly flattened call becomes a crack.
    const samples = Int16Array.from([30_000, -30_000]);
    applyGain(samples, 4);
    expect(samples[0]).toBe(FULL_SCALE);
    expect(samples[1]).toBe(-FULL_SCALE);
  });

  it("reports how much it had to clamp", () => {
    const samples = Int16Array.from([30_000, 100, -30_000]);
    expect(applyGain(samples, 4)).toBe(2);
  });

  it("does nothing at all when there is nothing to do", () => {
    const samples = Int16Array.from([123, -456]);
    expect(applyGain(samples, 1)).toBe(0);
    expect([...samples]).toEqual([123, -456]);
  });
});

describe("saying it out loud", () => {
  it("names the change", () => {
    expect(describeGain(planGain(tone(0.03)))).toMatch(/^\+\d+ dB$/);
  });

  it("stays quiet when the change is not worth mentioning", () => {
    expect(describeGain(planGain(tone(0.89)))).toBeUndefined();
  });
});
