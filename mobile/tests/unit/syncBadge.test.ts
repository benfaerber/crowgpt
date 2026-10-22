import { describe, expect, it } from "vitest";

import { captureId, syncBadge } from "../../src/ui/theme";
import type { CaptureRecord } from "../../src/domain/types";

/**
 * One badge, computed once.
 *
 * There were two implementations. The list row knew that an uploaded capture
 * with unpushed edits reads "Edited"; the detail screen — the screen you are on
 * when you make the edit — did not, and kept saying "Synced". That is exactly
 * how a working sync looks broken, and it cost a round of "is this even
 * saving?".
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
    localRevision: 0,
    syncedRevision: 0,
    ...patch,
  } as CaptureRecord;
}

describe("sync badge", () => {
  it("says Synced when the server has everything", () => {
    expect(syncBadge(capture({})).label).toBe("Synced");
  });

  it("says Edited once a synced capture is changed", () => {
    expect(syncBadge(capture({ localRevision: 3, syncedRevision: 2 })).label)
      .toBe("Edited");
  });

  it("keeps saying On phone for a capture that never synced", () => {
    // Edited is only meaningful against something the server already holds.
    expect(syncBadge(capture({ syncState: "local", localRevision: 3, syncedRevision: 0 })).label)
      .toBe("On phone");
  });

  it("does not hide a failure behind an edit", () => {
    expect(syncBadge(capture({ syncState: "failed", localRevision: 3, syncedRevision: 1 })).label)
      .toBe("Failed");
  });

  it("goes back to Synced once the edit lands", () => {
    expect(syncBadge(capture({ localRevision: 3, syncedRevision: 3 })).label)
      .toBe("Synced");
  });

  it("colours Edited apart from Synced, so the change is visible at a glance", () => {
    const synced = syncBadge(capture({}));
    const edited = syncBadge(capture({ localRevision: 1, syncedRevision: 0 }));
    expect(edited.color).not.toBe(synced.color);
  });
});

/**
 * What a capture is called outside this phone.
 *
 * The server id, because it is what the experiments resolve by, what `phases/`
 * cites, and what gets said out loud — "capture 104", never a uuid. It is
 * assigned by the server, so a capture that has not synced genuinely has no
 * name yet, and the caller has to be able to tell that from "the id is 0".
 */
describe("captureId", () => {
  it("names a synced capture by its server id", () => {
    expect(captureId(capture({ serverCaptureId: 104 }))).toBe("#104");
  });

  it("gives a capture the server has never seen no id at all", () => {
    // Undefined rather than "#" or "#undefined": the screens decide what to say
    // about a capture with no id, and they can only do that if they can see it.
    expect(captureId(capture({ serverCaptureId: undefined }))).toBeUndefined();
  });

  it("does not mistake id zero for no id", () => {
    // A falsy check here would hide capture #0. Unlikely from this server, and
    // exactly the kind of thing that survives until the one time it does not.
    expect(captureId(capture({ serverCaptureId: 0 }))).toBe("#0");
  });
});
