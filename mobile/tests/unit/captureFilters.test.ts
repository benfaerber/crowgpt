import { describe, expect, it } from "vitest";

import {
  applyView,
  DEFAULT_VIEW,
  describeView,
  rangeStart,
  type CaptureView,
} from "../../src/domain/captureFilters";
import type { CaptureRecord } from "../../src/domain/types";

/**
 * Narrowing the capture list.
 *
 * The interesting part is the day boundary. A capture made at 9am in Salt Lake
 * is 15:48Z and an evening one lands on the *next* UTC day, so a filter built
 * on UTC would drop the morning's work some hours and include yesterday's on
 * others — intermittent, and blamed on sync.
 */
const at = (recordedAt: string, patch: Partial<CaptureRecord> = {}): CaptureRecord =>
  ({
    uuid: recordedAt,
    mediaUuid: "m",
    recordedAt,
    durationMs: 1000,
    sampleRate: 48000,
    channels: 1,
    audioPath: "/tmp/a.wav",
    bytes: 100,
    syncState: "synced",
    uploadedBytes: 100,
    attempts: 0,
    keep: false,
    ...patch,
  }) as CaptureRecord;

// Late morning, Salt Lake (UTC-6). Anything recorded this evening is 27 July in
// UTC while still being "today" to the person holding the phone.
const NOW = new Date(2026, 6, 26, 11, 0, 0);

describe("date ranges", () => {
  it("starts today at local midnight, not UTC midnight", () => {
    const start = rangeStart("today", NOW)!;
    expect(start.getHours()).toBe(0);
    expect(start.getDate()).toBe(26);
  });

  it("keeps an evening recording in today, though UTC calls it tomorrow", () => {
    // 26 July 19:00 local is 27 July 01:00Z. The recordist made it today.
    const evening = at(new Date(2026, 6, 26, 19, 0, 0).toISOString());
    const shown = applyView([evening], { ...DEFAULT_VIEW, range: "today" }, NOW);
    expect(shown).toHaveLength(1);
  });

  it("excludes yesterday from today", () => {
    const yesterday = at(new Date(2026, 6, 25, 23, 30, 0).toISOString());
    expect(applyView([yesterday], { ...DEFAULT_VIEW, range: "today" }, NOW)).toEqual([]);
  });

  it("counts seven days, not 168 hours", () => {
    // Last Monday morning should not drop out of a week filter because it is
    // now Monday afternoon.
    const sevenDaysAgoMorning = at(new Date(2026, 6, 20, 8, 0, 0).toISOString());
    const shown = applyView([sevenDaysAgoMorning], { ...DEFAULT_VIEW, range: "week" }, NOW);
    expect(shown).toHaveLength(1);
  });

  it("drops the eighth day", () => {
    const tooOld = at(new Date(2026, 6, 19, 8, 0, 0).toISOString());
    expect(applyView([tooOld], { ...DEFAULT_VIEW, range: "week" }, NOW)).toEqual([]);
  });

  it("shows everything on all", () => {
    const old = at("2020-01-01T00:00:00Z");
    expect(applyView([old], DEFAULT_VIEW, NOW)).toHaveLength(1);
  });
});

describe("sorting", () => {
  const captures = [
    at("2026-07-24T10:00:00Z"),
    at("2026-07-26T10:00:00Z"),
    at("2026-07-25T10:00:00Z"),
  ];

  it("puts the newest first by default", () => {
    const shown = applyView(captures, DEFAULT_VIEW, NOW);
    expect(shown.map((c) => c.recordedAt.slice(0, 10)))
      .toEqual(["2026-07-26", "2026-07-25", "2026-07-24"]);
  });

  it("reverses on oldest", () => {
    const shown = applyView(captures, { ...DEFAULT_VIEW, order: "oldest" }, NOW);
    expect(shown.map((c) => c.recordedAt.slice(0, 10)))
      .toEqual(["2026-07-24", "2026-07-25", "2026-07-26"]);
  });

  it("orders by when it was recorded, not when it arrived", () => {
    // A capture restored from the server months later belongs beside the ones
    // it was recorded with.
    const restored = at("2026-07-25T10:00:00Z", { syncedAt: "2026-12-01T00:00:00Z" });
    const shown = applyView([at("2026-07-26T10:00:00Z"), restored], DEFAULT_VIEW, NOW);
    expect(shown[1].recordedAt).toBe("2026-07-25T10:00:00Z");
  });
});

describe("combining with the keep filter", () => {
  const captures = [
    at("2026-07-26T10:00:00Z", { keep: true }),
    at("2026-07-26T11:00:00Z", { keep: false }),
    at("2026-07-01T10:00:00Z", { keep: true }),
  ];

  it("applies both at once", () => {
    const view: CaptureView = { order: "newest", range: "today", keptOnly: true, unlabelledOnly: false };
    expect(applyView(captures, view, NOW)).toHaveLength(1);
  });
});

describe("saying what is hidden", () => {
  it("is quiet when nothing is filtered", () => {
    expect(describeView(DEFAULT_VIEW, 40, 40)).toBeUndefined();
  });

  it("names every active filter", () => {
    // A filter that looks like data loss is worse than no filter — four
    // captures out of forty was once reported as everything disappearing.
    const view: CaptureView = { order: "newest", range: "today", keptOnly: true, unlabelledOnly: false };
    expect(describeView(view, 1, 40)).toBe("Showing 1 of 40 — today, kept");
  });
});

describe("bad data", () => {
  it("keeps a capture with an unparseable date rather than losing it", () => {
    // Losing a recording to a bad date field is worse than showing one out of
    // range, and the recordist can see the row to fix it.
    const broken = at("not-a-date");
    expect(applyView([broken], { ...DEFAULT_VIEW, range: "today" }, NOW)).toHaveLength(1);
  });
});

describe("the label queue as a filter", () => {
  it("counts as narrowing, and says so", () => {
    // Otherwise the list drops to the handful waiting and the banner stays
    // silent — which is the shape of the bug this banner was added for.
    const view: CaptureView = { ...DEFAULT_VIEW, unlabelledOnly: true };
    expect(describeView(view, 2, 40)).toBe("Showing 2 of 40 — waiting to be labelled");
  });

  it("names itself alongside the other filters", () => {
    const view: CaptureView = {
      order: "newest", range: "today", keptOnly: true, unlabelledOnly: true,
    };
    expect(describeView(view, 1, 40))
      .toBe("Showing 1 of 40 — today, kept, waiting to be labelled");
  });
});
