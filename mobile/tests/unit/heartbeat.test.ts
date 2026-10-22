import { describe, expect, it } from "vitest";

import {
  HEARTBEAT_MAX_SEC,
  HEARTBEAT_MIN_SEC,
  normalizeHeartbeatSeconds,
} from "../../src/domain/heartbeat";

describe("normalizeHeartbeatSeconds", () => {
  it("reads the box as a whole number of seconds", () => {
    expect(normalizeHeartbeatSeconds("10", 30)).toBe(10);
    expect(normalizeHeartbeatSeconds("  45 ", 30)).toBe(45);
  });

  it("clamps rather than rejects — '3' wanted fast and gets the fastest offered", () => {
    expect(normalizeHeartbeatSeconds("3", 30)).toBe(HEARTBEAT_MIN_SEC);
    expect(normalizeHeartbeatSeconds("0", 30)).toBe(HEARTBEAT_MIN_SEC);
    expect(normalizeHeartbeatSeconds("100000", 30)).toBe(HEARTBEAT_MAX_SEC);
  });

  it("a box blurred mid-edit must not move the setting", () => {
    expect(normalizeHeartbeatSeconds("", 30)).toBe(30);
    expect(normalizeHeartbeatSeconds("often", 30)).toBe(30);
    expect(normalizeHeartbeatSeconds("-", 30)).toBe(30);
  });

  it("a negative number is a mistake, not a request for silence", () => {
    // Zero and below would read as "off", but off is the toggle's job — a
    // number that disabled the feature from the text box would be two
    // controls for one setting, disagreeing.
    expect(normalizeHeartbeatSeconds("-10", 30)).toBe(HEARTBEAT_MIN_SEC);
  });
});
