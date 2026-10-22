import { describe, expect, it } from "vitest";

import { mappableCaptures } from "../../src/ui/map/mapHtml";
import type { CaptureRecord } from "../../src/domain/types";

/**
 * What the map is allowed to show.
 *
 * Seeded clips carry fabricated coordinates, so an unfiltered map is mostly
 * pins for audio that was never recorded anywhere near here. The star is the
 * only thing separating those from real fieldwork.
 */
function capture(patch: Partial<CaptureRecord>): CaptureRecord {
  return {
    uuid: "c1",
    mediaUuid: "m1",
    recordedAt: "2026-07-26T09:00:00Z",
    durationMs: 3000,
    sampleRate: 48000,
    channels: 1,
    audioPath: "/tmp/a.wav",
    bytes: 1000,
    syncState: "synced",
    uploadedBytes: 1000,
    attempts: 0,
    keep: false,
    ...patch,
  } as CaptureRecord;
}

describe("map pins", () => {
  it("places only captures that have a fix", () => {
    const placed = mappableCaptures([
      capture({ uuid: "with", latitude: 40.76, longitude: -111.87 }),
      capture({ uuid: "without" }),
    ], undefined, "exact", false);
    expect(placed.map((p) => p.uuid)).toEqual(["with"]);
  });

  it("carries the keep flag through, so the caller can filter on it", () => {
    const placed = mappableCaptures([
      capture({ uuid: "real", latitude: 40.76, longitude: -111.87, keep: true }),
    ], undefined, "exact", false);
    expect(placed[0].keep).toBe(true);
  });

  it("stars a kept pin's label", () => {
    // Leading, as in the capture list: on a map of mostly seeded pins, "is this
    // real?" is the first thing worth knowing about a marker.
    const [pin] = mappableCaptures([
      capture({ latitude: 40.76, longitude: -111.87, keep: true }),
    ], undefined, "exact", false);
    expect(pin.label.startsWith("★ ")).toBe(true);
  });

  it("leaves an unkept pin's label alone", () => {
    const [pin] = mappableCaptures([
      capture({ latitude: 40.76, longitude: -111.87, keep: false }),
    ], undefined, "exact", false);
    expect(pin.label.startsWith("★")).toBe(false);
  });

  it("filtering to kept drops the seeded pins", () => {
    const all = [
      capture({ uuid: "seeded", latitude: 1, longitude: 1, keep: false }),
      capture({ uuid: "field", latitude: 2, longitude: 2, keep: true }),
    ];
    const kept = mappableCaptures(all.filter((c) => c.keep), undefined, "exact", false);
    expect(kept.map((p) => p.uuid)).toEqual(["field"]);
  });
});
