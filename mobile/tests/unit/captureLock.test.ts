import { describe, expect, it } from "vitest";

import { screenLocked, unlockReached, UNLOCK_FRACTION } from "../../src/domain/captureLock";

describe("screenLocked", () => {
  it("covers the screen while recording", () => {
    expect(screenLocked({ enabled: true, recording: true, unlocked: false })).toBe(true);
  });

  it("leaves an idle screen alone", () => {
    // A stray touch that starts a recording costs disk and is undone by
    // deleting it. That is not the loss this exists to prevent.
    expect(screenLocked({ enabled: true, recording: false, unlocked: false })).toBe(false);
  });

  it("stays open once unlocked for this capture", () => {
    expect(screenLocked({ enabled: true, recording: true, unlocked: true })).toBe(false);
  });

  it("does nothing when the setting is off", () => {
    expect(screenLocked({ enabled: false, recording: true, unlocked: false })).toBe(false);
  });
});

describe("unlockReached", () => {
  const travel = 300;

  it("unlocks on a drag that crosses almost the whole track", () => {
    expect(unlockReached(travel, travel)).toBe(true);
  });

  it("refuses a tap", () => {
    expect(unlockReached(0, travel)).toBe(false);
  });

  it("refuses a half-way smear", () => {
    expect(unlockReached(travel / 2, travel)).toBe(false);
  });

  it("refuses a drag that stops just short", () => {
    expect(unlockReached(travel * UNLOCK_FRACTION - 1, travel)).toBe(false);
  });

  it("refuses a leftward drag", () => {
    expect(unlockReached(-travel, travel)).toBe(false);
  });

  /**
   * Before onLayout has measured the track there is no distance to cross, and a
   * naive `dx >= travel * fraction` makes every touch an unlock — including the
   * first one after the overlay appears, which is the worst possible moment.
   */
  it("refuses everything before the track has been measured", () => {
    expect(unlockReached(0, 0)).toBe(false);
    expect(unlockReached(500, 0)).toBe(false);
  });

  it("keeps the threshold high enough to be a deliberate gesture", () => {
    expect(UNLOCK_FRACTION).toBeGreaterThanOrEqual(0.8);
  });
});
