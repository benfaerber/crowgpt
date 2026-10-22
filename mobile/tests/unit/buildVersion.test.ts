import { describe, expect, it } from "vitest";

import {
  formatAge,
  formatCommitTime,
  formatVersion,
  UNKNOWN_BUILD,
  type BuildInfo,
} from "../../src/app/buildVersion";

function build(overrides: Partial<BuildInfo> = {}): BuildInfo {
  return {
    version: 100,
    commit: "73c083f",
    committedAt: "2026-07-25T18:19:00Z",
    dirty: false,
    ...overrides,
  };
}

describe("formatVersion", () => {
  it("counts commits, so the hundredth commit is v100", () => {
    expect(formatVersion(build({ version: 100 }))).toBe("v100 · 73c083f");
  });

  it("starts at v1 for the first commit", () => {
    expect(formatVersion(build({ version: 1, commit: "8ae3f19" }))).toBe("v1 · 8ae3f19");
  });

  it("marks a build made from uncommitted edits", () => {
    // Such a build cannot be reproduced from its hash, so the hash alone would
    // be a lie about what is running.
    expect(formatVersion(build({ dirty: true }))).toBe("v100 · 73c083f +local edits");
  });

  it("says so plainly when git was unavailable", () => {
    expect(formatVersion(UNKNOWN_BUILD)).toBe("unversioned · unknown");
  });

  it("never reports v0 as a real version", () => {
    expect(formatVersion(build({ version: 0 }))).not.toContain("v0");
  });
});

describe("formatCommitTime", () => {
  it("reports when the code was written, with its age", () => {
    const now = new Date("2026-07-25T20:19:00Z");
    expect(formatCommitTime(build(), now)).toContain("(2h ago)");
  });

  it("is undefined when git gave no timestamp", () => {
    expect(formatCommitTime(build({ committedAt: undefined }))).toBeUndefined();
  });

  it("is undefined rather than 'Invalid Date' for a malformed stamp", () => {
    expect(formatCommitTime(build({ committedAt: "not-a-date" }))).toBeUndefined();
  });
});

describe("formatAge", () => {
  const committed = new Date("2026-07-25T18:19:00Z");

  it.each([
    ["30 seconds", 30 * 1000, "just now"],
    ["9 minutes", 9 * 60_000, "9m ago"],
    ["59 minutes", 59 * 60_000, "59m ago"],
    ["1 hour", 60 * 60_000, "1h ago"],
    ["23 hours", 23 * 60 * 60_000, "23h ago"],
    ["1 day", 24 * 60 * 60_000, "yesterday"],
    ["5 days", 5 * 24 * 60 * 60_000, "5d ago"],
  ])("renders %s as %s", (_label, elapsedMs, expected) => {
    const now = new Date(committed.getTime() + (elapsedMs as number));
    expect(formatAge(committed, now)).toBe(expected);
  });

  it("does not report a negative age when the phone's clock is behind", () => {
    const now = new Date(committed.getTime() - 60 * 60_000);
    expect(formatAge(committed, now)).toBe("just now");
  });
});
