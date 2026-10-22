import { describe, expect, it } from "vitest";

import { MemoryContextRepository } from "../../src/data/MemoryContextRepository";
import { MemoryLabelRepository } from "../../src/data/MemoryLabelRepository";
import { colorForCall, FALLBACK_CONFIG, labelText } from "../../src/domain/config";
import type { FleetConfig } from "../../src/domain/config";
import type { NewContext } from "../../src/domain/context";
import { isPendingSync, type NewLabel } from "../../src/domain/labels";

const SERVED: FleetConfig = {
  version: 3,
  locale: "en",
  core_classes: ["alarm call", "call", "flight call", "song"],
  caller_roles: [],
  core_colors: {
    "alarm call": "#f27070",
    call: "#6ea8fe",
    "flight call": "#6bd28a",
    song: "#c58af9",
  },
  labels: [
    { key: "alarm call", core: "alarm call", text: "Alarm call" },
    { key: "call", core: "call", text: "Call" },
    { key: "mobbing", core: "alarm call", text: "Mobbing" },
    { key: "rattle", core: "call", text: "Rattle" },
  ],
  contexts: [],
  observer_roles: [],
  instructions: [],
  guide: [],
  taxonomy: [],
};

function label(overrides: Partial<NewLabel> = {}): NewLabel {
  return {
    uuid: "lab-1",
    captureUuid: "cap-1",
    callType: "call",
    species: "American Crow",
    startSec: 4,
    endSec: 6,
    createdAt: "2026-07-25T18:00:00Z",
    ...overrides,
  };
}

describe("call colours come from the served config", () => {
  it("colours a core class directly", () => {
    expect(colorForCall(SERVED, "alarm call")).toBe("#f27070");
  });

  it("colours an operator-defined label by the core it maps to", () => {
    // The hardcoded table this replaced had never heard of "mobbing", so it
    // fell to grey despite being an alarm.
    expect(colorForCall(SERVED, "mobbing")).toBe("#f27070");
    expect(colorForCall(SERVED, "rattle")).toBe("#6ea8fe");
  });

  it("leaves an unknown type grey rather than borrowing a colour", () => {
    // Borrowing would imply a classification we do not have.
    expect(colorForCall(SERVED, "kraa")).toBe("#9aa5b1");
    expect(colorForCall(SERVED, null)).toBe("#9aa5b1");
  });

  it("still works before the first fetch", () => {
    // A phone that has never reached the server can label the CORE classes —
    // exactly those, so promoting one (begging) reaches an unsynced phone too.
    expect(colorForCall(FALLBACK_CONFIG, "song")).toBe("#c58af9");
    expect(FALLBACK_CONFIG.labels.map((l) => l.key)).toEqual(
      FALLBACK_CONFIG.core_classes,
    );
    expect(Object.keys(FALLBACK_CONFIG.core_colors).sort()).toEqual(
      [...FALLBACK_CONFIG.core_classes].sort(),
    );
  });

  it("gives begging its own colour rather than the call one", () => {
    // It used to map down to `call`, which hid a distinct juvenile category
    // inside the largest, vaguest class.
    expect(colorForCall(FALLBACK_CONFIG, "begging")).not.toBe(
      colorForCall(FALLBACK_CONFIG, "call"),
    );
  });

  it("shows the served display text, not the key", () => {
    expect(labelText(SERVED, "mobbing")).toBe("Mobbing");
    expect(labelText(SERVED, "kraa")).toBe("kraa");
  });
});

describe("labels are stored locally first", () => {
  it("keeps a new label pending until the server accepts it", async () => {
    const labels = new MemoryLabelRepository();
    const stored = await labels.add(label());
    expect(isPendingSync(stored)).toBe(true);
    expect(await labels.pendingSync()).toHaveLength(1);
  });

  it("settles once the server has it", async () => {
    const labels = new MemoryLabelRepository();
    await labels.add(label());
    await labels.update("lab-1", { serverId: 7, syncedAt: "2026-07-25T19:00:00Z" });
    expect(await labels.pendingSync()).toHaveLength(0);
  });

  it("returns a capture's labels in time order", async () => {
    const labels = new MemoryLabelRepository();
    await labels.add(label({ uuid: "b", startSec: 30, endSec: 32 }));
    await labels.add(label({ uuid: "a", startSec: 4, endSec: 6 }));
    expect((await labels.forCapture("cap-1")).map((l) => l.uuid)).toEqual(["a", "b"]);
  });

  it("keeps captures' labels apart", async () => {
    const labels = new MemoryLabelRepository();
    await labels.add(label({ uuid: "mine" }));
    await labels.add(label({ uuid: "theirs", captureUuid: "cap-2" }));
    expect(await labels.forCapture("cap-1")).toHaveLength(1);
  });

  it("can be retracted", async () => {
    // Ground truth that cannot be taken back is worse than none.
    const labels = new MemoryLabelRepository();
    await labels.add(label());
    await labels.remove("lab-1");
    expect(await labels.forCapture("cap-1")).toHaveLength(0);
  });

  it("re-pends everything when the server changes", async () => {
    // Remembered ids belonged to a server we are no longer talking to.
    const labels = new MemoryLabelRepository();
    await labels.add(label());
    await labels.update("lab-1", { serverId: 7 });
    await labels.forgetServerState();
    expect(await labels.pendingSync()).toHaveLength(1);
  });
});

describe("context belongs to a call, not a recording", () => {
  /**
   * The distinction the whole semantics axis rests on. A two-minute capture
   * might have a dog appear at 0:30 and leave at 0:50 — the alarm calls in that
   * window are about the dog, the song at 1:40 is not. Attaching context to the
   * capture would credit every situation to every call in it, and the
   * co-occurrence table would report that crows sing at dogs.
   */
  const event = (overrides: Partial<NewContext> = {}): NewContext => ({
    uuid: "ctx-1",
    captureUuid: "cap-1",
    labelUuid: "lab-alarm",
    key: "dog_visible",
    createdAt: "2026-07-25T18:00:00Z",
    ...overrides,
  });

  it("keeps two calls in one capture apart", async () => {
    const context = new MemoryContextRepository();
    await context.add(event({ uuid: "a", labelUuid: "lab-alarm", key: "dog_visible" }));
    await context.add(
      event({ uuid: "b", labelUuid: "lab-song", key: "nothing_obvious" }),
    );

    expect((await context.forLabel("lab-alarm")).map((e) => e.key)).toEqual([
      "dog_visible",
    ]);
    expect((await context.forLabel("lab-song")).map((e) => e.key)).toEqual([
      "nothing_obvious",
    ]);
  });

  it("still lists everything witnessed in a capture", async () => {
    const context = new MemoryContextRepository();
    await context.add(event({ uuid: "a", labelUuid: "lab-alarm" }));
    await context.add(event({ uuid: "b", labelUuid: "lab-song" }));
    expect(await context.forCapture("cap-1")).toHaveLength(2);
  });

  it("lets one call carry several situations", async () => {
    const context = new MemoryContextRepository();
    await context.add(event({ uuid: "a", key: "dog_visible" }));
    await context.add(event({ uuid: "b", key: "stranger_passing" }));
    expect(await context.forLabel("lab-alarm")).toHaveLength(2);
  });

  it("holds a new event until the server takes it", async () => {
    const context = new MemoryContextRepository();
    await context.add(event());
    expect(await context.pendingSync()).toHaveLength(1);
  });
});

/**
 * Comparing a call in hand against ones already decided.
 *
 * Consistency across a season is the hard part of hand-labelling: the same
 * sound marked `alarm call` in July and `scold` in November is not two data
 * points, it is noise with a label on it.
 */
describe("finding previous examples", () => {
  // createdAt defaulted: the ordering tests pass one because ordering is what
  // they are about, and the caller tests do not care when the label was made.
  const label = (uuid: string, callType: string,
                 createdAt = "2026-07-25T18:00:00Z") => ({
    uuid,
    captureUuid: `cap-${uuid}`,
    callType,
    species: "American Crow",
    startSec: 1,
    endSec: 3,
    createdAt,
  });

  it("finds examples across every capture, not just this one", async () => {
    // The point of it: the useful comparison is almost never in the recording
    // being labelled.
    const labels = new MemoryLabelRepository();
    await labels.add(label("a", "alarm call", "2026-07-01T00:00:00Z"));
    await labels.add(label("b", "alarm call", "2026-07-20T00:00:00Z"));
    const found = await labels.byCallType("alarm call");
    expect(found.map((l) => l.uuid).sort()).toEqual(["a", "b"]);
  });

  it("returns the most recent first", async () => {
    // A recent example is likelier to be the same birds in the same place,
    // which is what makes it worth comparing against.
    const labels = new MemoryLabelRepository();
    await labels.add(label("old", "alarm call", "2026-01-01T00:00:00Z"));
    await labels.add(label("new", "alarm call", "2026-07-20T00:00:00Z"));
    expect((await labels.byCallType("alarm call"))[0].uuid).toBe("new");
  });

  it("does not mix call types", async () => {
    const labels = new MemoryLabelRepository();
    await labels.add(label("a", "alarm call", "2026-07-01T00:00:00Z"));
    await labels.add(label("b", "song", "2026-07-02T00:00:00Z"));
    expect(await labels.byCallType("song")).toHaveLength(1);
  });

  it("caps how many it returns", async () => {
    const labels = new MemoryLabelRepository();
    for (let i = 0; i < 12; i += 1) {
      await labels.add(label(`l${i}`, "alarm call", `2026-07-${10 + i}T00:00:00Z`));
    }
    expect(await labels.byCallType("alarm call", 3)).toHaveLength(3);
  });

  it("says nothing rather than guessing when the type is new", async () => {
    expect(await new MemoryLabelRepository().byCallType("begging")).toEqual([]);
  });

  it("carries the caller, and keeps blank distinct from a value", async () => {
    // The whole point of the field. An unset caller means nobody looked; it
    // must never become a value, because experiment 0017 established the audio
    // cannot recover one and a guess is indistinguishable from an observation
    // a year later.
    const labels = new MemoryLabelRepository();
    const seen = await labels.add({
      ...label("l1", "begging"),
      callerRole: "fledgling",
    });
    const unseen = await labels.add(label("l2", "begging"));

    expect(seen.callerRole).toBe("fledgling");
    expect(unseen.callerRole).toBeUndefined();
  });

  it("lets a caller be cleared back to nobody-looked", async () => {
    // Tapping the chosen role again is the undo, and it has to return the row
    // to absent rather than to an empty string — which would read as an answer.
    const labels = new MemoryLabelRepository();
    await labels.add({ ...label("l1", "begging"), callerRole: "parent" });
    const cleared = await labels.update("l1", { callerRole: undefined });
    expect(cleared.callerRole).toBeUndefined();
  });
});
