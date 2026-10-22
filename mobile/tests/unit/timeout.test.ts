import { describe, expect, it, vi } from "vitest";

import { withTimeout } from "../../src/domain/timeout";

describe("withTimeout", () => {
  it("passes a value through when it arrives in time", async () => {
    await expect(withTimeout(Promise.resolve("fix"), 1000, "none")).resolves.toBe("fix");
  });

  /**
   * The one that matters. `getCurrentPositionAsync` does not resolve indoors,
   * and stopping a recording awaited it while holding the guard that makes the
   * earbud button work — so a fix that never arrived left the button dead with
   * nothing on screen to say why.
   */
  it("gives up on a promise that never settles", async () => {
    vi.useFakeTimers();
    try {
      const never = new Promise<string>(() => {});
      const raced = withTimeout(never, 15_000, "none");
      await vi.advanceTimersByTimeAsync(15_000);
      await expect(raced).resolves.toBe("none");
    } finally {
      vi.useRealTimers();
    }
  });

  it("treats a rejection as an absent value", async () => {
    await expect(
      withTimeout(Promise.reject(new Error("no signal")), 1000, "none"),
    ).resolves.toBe("none");
  });

  it("keeps the first answer when the slow one arrives later", async () => {
    vi.useFakeTimers();
    try {
      let settle: (value: string) => void = () => {};
      const late = new Promise<string>((resolve) => {
        settle = resolve;
      });
      const raced = withTimeout(late, 1000, "none");
      await vi.advanceTimersByTimeAsync(1000);
      settle("too late");
      await expect(raced).resolves.toBe("none");
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not leave a timer running after a fast answer", async () => {
    vi.useFakeTimers();
    try {
      await expect(withTimeout(Promise.resolve("fix"), 1000, "none")).resolves.toBe("fix");
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });
});
