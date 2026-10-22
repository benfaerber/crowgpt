import { describe, expect, it } from "vitest";

import {
  addPending,
  settlePending,
  type PendingCapture,
} from "../../src/domain/pendingCaptures";

const audio = (id: string): PendingCapture => ({ id, kind: "audio", durationMs: 8000 });

/**
 * The rule that matters is the one about getting rid of them.
 *
 * A placeholder exists to say "a recording was made and is being written down".
 * One that outlives the writing says something false, and says it permanently:
 * a "Loading…" over a capture that will never arrive. Every path that puts one
 * up runs its removal from a `finally`, which means removal has to survive
 * being called twice and being called for something already gone.
 */
describe("pending captures", () => {
  it("stands a placeholder in the list", () => {
    expect(addPending([], audio("a"))).toHaveLength(1);
  });

  it("keeps them in the order they were made", () => {
    const list = addPending(addPending([], audio("a")), audio("b"));
    expect(list.map((entry) => entry.id)).toEqual(["a", "b"]);
  });

  it("settles only the one named", () => {
    const list = addPending(addPending([], audio("a")), audio("b"));
    expect(settlePending(list, "a").map((entry) => entry.id)).toEqual(["b"]);
  });

  it("tolerates settling the same placeholder twice", () => {
    // The error path and the finally both clear it, so this is the ordinary
    // case rather than an edge one.
    const once = settlePending(addPending([], audio("a")), "a");
    expect(settlePending(once, "a")).toEqual([]);
  });

  it("tolerates settling one that was never added", () => {
    expect(settlePending([], "never-existed")).toEqual([]);
  });

  it("does not mutate the list it was given", () => {
    // The list is React state; mutating it in place is how a row fails to
    // disappear until something unrelated re-renders the screen.
    const before = addPending([], audio("a"));
    settlePending(before, "a");
    expect(before).toHaveLength(1);
  });

  it("carries the length it already knows", () => {
    // Known before the row exists, because it comes back with the closed file.
    const [entry] = addPending([], audio("a"));
    expect(entry.durationMs).toBe(8000);
  });

  it("remembers which button made it", () => {
    const [entry] = addPending([], { id: "v", kind: "video" });
    expect(entry.kind).toBe("video");
    expect(entry.durationMs).toBeUndefined();
  });
});
