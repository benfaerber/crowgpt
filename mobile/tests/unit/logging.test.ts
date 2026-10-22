import { describe, expect, it, vi } from "vitest";

import { Log } from "../../src/app/Log";
import { MemoryLogRepository } from "../../src/data/MemoryLogRepository";
import { LogRing, describeError } from "../../src/domain/logging";
import { LogSync } from "../../src/sync/LogSync";
import type { FieldServerClient } from "../../src/net/FieldServerClient";

const bytes = (length: number) =>
  Uint8Array.from({ length }, (_, index) => (index * 7) % 251);

/** A logger with storage attached, flushed on demand rather than on a timer. */
async function attached() {
  const store = new MemoryLogRepository();
  const log = new Log();
  log.attach(store, bytes);
  return { log, store };
}

describe("the ring", () => {
  it("keeps the newest when it overflows", () => {
    // A crash loop writes the same line thousands of times a minute. The last
    // ones are the ones that describe what is happening now.
    const ring = new LogRing(3);
    for (const n of [1, 2, 3, 4, 5]) {
      ring.add({ uuid: `u${n}`, at: "", level: "info", tag: "t", message: `${n}` });
    }
    expect(ring.all().map((entry) => entry.message)).toEqual(["3", "4", "5"]);
  });

  it("hands everything over on drain and forgets it", () => {
    const ring = new LogRing();
    ring.add({ uuid: "u", at: "", level: "info", tag: "t", message: "one" });
    expect(ring.drain()).toHaveLength(1);
    expect(ring.size).toBe(0);
  });
});

describe("describing what was thrown", () => {
  it("keeps the stack, which is the part worth having", () => {
    const described = describeError(new TypeError("null is not an object"));
    expect(described.message).toBe("TypeError: null is not an object");
    expect((described.detail as { stack?: string }).stack).toContain("TypeError");
  });

  it("does not reduce a native rejection to [object Object]", () => {
    // Native module rejections arrive as bare objects with a code. String()
    // turns them into "[object Object]", which is how a logged failure becomes
    // indistinguishable from no failure.
    const described = describeError({ code: "ERR_MIC_BUSY", nativeStackAndroid: [] });
    expect(described.message).toContain("ERR_MIC_BUSY");
  });

  it("survives undefined", () => {
    expect(describeError(undefined).message).toBe("undefined");
  });
});

describe("the logger", () => {
  it("accepts entries before there is anywhere to put them", async () => {
    // The failure it most needs to catch is the store failing to open.
    const log = new Log();
    log.useRandomBytes(bytes);
    log.error("db", "openDatabaseAsync threw", new Error("NullPointerException"));
    expect(log.buffered).toBe(1);

    const store = new MemoryLogRepository();
    log.attach(store, bytes);
    await log.flush();
    expect((await store.recent())[0].message).toContain("NullPointerException");
  });

  it("retries entries the store rejected once it comes back", async () => {
    const { log, store } = await attached();
    store.failing = true;
    log.warn("recorder", "mic fell back");
    await log.flush();
    expect(log.buffered).toBe(1);

    store.failing = false;
    await log.flush();
    expect(await store.countPending()).toBe(1);
  });

  it("does not throw when the id source is broken", async () => {
    // expo-crypto is a native module, and a native module may be exactly what
    // is broken at the moment something is being logged.
    const { log, store } = await attached();
    log.useRandomBytes(() => {
      throw new Error("no crypto in Hermes");
    });
    log.info("app", "still logged");
    await log.flush();
    expect(await store.countPending()).toBe(1);
  });

  it("folds the thrown value into the message and the detail", async () => {
    const { log, store } = await attached();
    log.error("sync", "run threw", new Error("timeout"), { capture: "abc" });
    await log.flush();
    const [entry] = await store.recent();
    expect(entry.message).toBe("run threw — Error: timeout");
    expect(entry.detail).toMatchObject({ capture: "abc" });
    expect((entry.detail as { stack?: string }).stack).toBeTruthy();
  });

  it("takes the first Error out of a console call rather than stringifying it", async () => {
    const { log, store } = await attached();
    log.fromConsole("error", ["Warning: render failed", new Error("boom"), 42]);
    await log.flush();
    const [entry] = await store.recent();
    expect(entry.message).toContain("Warning: render failed");
    expect(entry.message).toContain("Error: boom");
  });

  it("does not log its own logging", async () => {
    // console.error is intercepted, so a logger that itself logged through
    // console would be a loop with no exit.
    const { log, store } = await attached();
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    log.info("app", "circular detail", circular);
    await log.flush();
    expect(await store.countPending()).toBe(1);
  });
});

describe("sending them up", () => {
  const client = (pushLogs: unknown) => ({ pushLogs }) as unknown as FieldServerClient;

  it("counts what the server named, and leaves the queue drained either way", async () => {
    // A line the server refused, it will refuse identically forever — so the
    // batch is cleared regardless. Marking only the accepted ones leaves the
    // rest at the head of the queue and every later run re-sends them without
    // ever advancing.
    const store = new MemoryLogRepository();
    await store.append([
      { uuid: "a", at: "1", level: "info", tag: "t", message: "one" },
      { uuid: "b", at: "2", level: "info", tag: "t", message: "two" },
    ]);
    const push = vi.fn().mockResolvedValue({ accepted: ["a"], rejected: [{ client_uuid: "b" }] });

    const outcome = await new LogSync(store, client(push)).run();

    expect(outcome.sent).toBe(1);
    expect(await store.countPending()).toBe(0);
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("returns a failure instead of throwing it", async () => {
    // A diagnostic upload that could fail a sync carrying a field recording has
    // inverted its own purpose.
    const store = new MemoryLogRepository();
    await store.append([{ uuid: "a", at: "1", level: "info", tag: "t", message: "one" }]);
    const push = vi.fn().mockRejectedValue(new Error("network down"));

    const outcome = await new LogSync(store, client(push)).run();

    expect(outcome.error).toBe("network down");
    expect(await store.countPending()).toBe(1);
  });

  it("does not loop forever on a line the server will never take", async () => {
    const store = new MemoryLogRepository();
    await store.append([{ uuid: "", at: "1", level: "info", tag: "t", message: "bad" }]);
    const push = vi.fn().mockResolvedValue({ accepted: [], rejected: [{ client_uuid: null }] });

    const outcome = await new LogSync(store, client(push)).run();

    expect(outcome.sent).toBe(0);
    expect(await store.countPending()).toBe(0);
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("sends nothing when there is nothing", async () => {
    const push = vi.fn();
    const outcome = await new LogSync(new MemoryLogRepository(), client(push)).run();
    expect(outcome).toEqual({ sent: 0 });
    expect(push).not.toHaveBeenCalled();
  });
});
