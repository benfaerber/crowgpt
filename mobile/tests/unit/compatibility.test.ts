import { describe, expect, it } from "vitest";

import { compatibility, REQUIRED_WIRE_VERSION } from "../../src/domain/compatibility";

/**
 * The failure this guards, observed rather than imagined: a v127 phone pushed to
 * a v123 server, which accepted every request and dropped the fields it did not
 * recognise. Unknown JSON keys are not an error. The phone marked those captures
 * delivered and nothing on either screen said a word.
 */
describe("server compatibility", () => {
  const at = (wire: number) => ({ version: 999, wire });

  it("accepts a server that speaks what this app needs", () => {
    expect(compatibility(at(REQUIRED_WIRE_VERSION)).serverBehind).toBe(false);
  });

  it("rejects a server that speaks less", () => {
    const result = compatibility(at(REQUIRED_WIRE_VERSION - 1));
    expect(result.serverBehind).toBe(true);
    expect(result.warning).toContain(`v${REQUIRED_WIRE_VERSION}`);
  });

  it("accepts a server ahead of this app", () => {
    // Normal in development — the laptop is always rebuilt first. Only behind
    // loses data, and warning on ahead would fire constantly.
    expect(compatibility(at(REQUIRED_WIRE_VERSION + 5)).serverBehind).toBe(false);
  });

  it("ignores the commit count entirely", () => {
    // The bug in the first version of this: three tooling commits ahead on the
    // phone flagged a server that stored exactly the same fields. A warning
    // that fires on unrelated work is one people learn to click past.
    expect(compatibility({ version: 1, wire: REQUIRED_WIRE_VERSION }).serverBehind)
      .toBe(false);
    expect(compatibility({ version: 99999, wire: 1 }).serverBehind).toBe(true);
  });

  it("treats a server that reports no wire version as too old", () => {
    // Not unknown: the field itself postdates the problem, so its absence is a
    // definite answer about how old that server is.
    expect(compatibility({ version: 120 }).serverBehind).toBe(true);
  });

  it("claims nothing when the server could not be reached", () => {
    // A phone with no signal has nothing to say, and blocking a sync that was
    // never going to happen helps nobody.
    expect(compatibility(undefined).serverBehind).toBe(false);
  });

  it("names the fix rather than just the problem", () => {
    expect(compatibility(at(1)).warning).toContain("Restart the field server");
  });

  it("refuses a server that cannot store a caller", () => {
    // v18 accepts the label and drops crow_id/caller_role, so the app would
    // show the attribution saved while the corpus never received it. Worse than
    // the usual silent loss: 0017 showed the audio does not carry the caller,
    // so what is dropped here cannot be reconstructed by anyone afterwards.
    expect(compatibility(at(18)).serverBehind).toBe(true);
  });

  it("refuses a server that would mislabel snapped coordinates", () => {
    // v21 accepts a fuzzed contributor's snapped coordinates and drops the
    // coord_fuzz_miles beside them, storing fixes a few miles wide that read
    // as exact forever — the same accept-and-mislabel shape as 18.
    expect(compatibility(at(21)).serverBehind).toBe(true);
  });

  it("refuses a server that would launder an auto capture into a witnessed one", () => {
    // v22 accepts an idle-mode capture and drops trigger="auto" beside it, so an
    // unattended recording — role and distance blank on purpose, possibly a
    // siren — reads as a deliberate field recording forever. Same
    // accept-and-mislabel shape as 18 and 22.
    expect(compatibility(at(22)).serverBehind).toBe(true);
    expect(compatibility(at(23)).serverBehind).toBe(false);
  });
});
