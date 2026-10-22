import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { MemoryAnalysisCache } from "../../src/data/MemoryAnalysisCache";

const DATA = join(__dirname, "../../src/data");

/**
 * One handle on the phone's database, and only openStore may take it.
 *
 * expo-sqlite caches connections by path: opening `cawtalker.db` twice hands
 * back the *same* native connection, reference counted. But the reference count
 * only guards the explicit close — when a JS handle is garbage collected,
 * `NativeDatabase.sharedObjectDidRelease` calls `ref.close()` outright, and the
 * connection every other store is using goes with it.
 *
 * Eight stores each opened their own, so the first one Hermes collected closed
 * the database for all of them. Every query afterwards prepared a statement
 * against a closed connection: a NullPointerException in `prepareAsync`, at a
 * random moment, worse on the phone with the most captures — and almost
 * certainly the capture list that twice went empty and then came back.
 *
 * A source-level test because the failure is a *shape* rather than a behaviour,
 * and because nothing here can be exercised on the host: expo-sqlite needs a
 * device. It costs one read per file and it fails the moment somebody adds a
 * ninth store the quick way.
 */
describe("the database handle", () => {
  const sources = readdirSync(DATA)
    .filter((name) => name.endsWith(".ts"))
    .map((name) => ({ name, body: readFileSync(join(DATA, name), "utf8") }));

  it("has more than one store to be shared between", () => {
    // Guards the guard: a glob that matched nothing would pass silently.
    const stores = sources.filter(({ body }) => body.includes("openStore("));
    expect(stores.length).toBeGreaterThan(3);
  });

  it("is opened in exactly one place", () => {
    const openers = sources
      .filter(({ body }) => body.includes("openDatabaseAsync"))
      .map(({ name }) => name);
    expect(openers).toEqual(["openStore.ts"]);
  });
});

describe("the analysis cache", () => {
  it("hands back what it was given", async () => {
    const cache = new MemoryAnalysisCache();
    await cache.save("cap-1", {
      calls: [{ start_sec: 1, end_sec: 2, species: "American Crow" }],
      waveform: [0.1, 0.9],
      duration: 18.4,
    });
    const found = await cache.get("cap-1");
    expect(found?.calls).toHaveLength(1);
    expect(found?.duration).toBe(18.4);
    expect(found?.fetchedAt).toBeTruthy();
  });

  it("replaces rather than merges, so an empty answer clears stale calls", async () => {
    // "The server has analyzed this and found nothing" is an answer. Showing
    // last week's calls beside it would be the lie a cache is most prone to.
    const cache = new MemoryAnalysisCache();
    await cache.save("cap-1", {
      calls: [{ start_sec: 1, end_sec: 2, species: "American Crow" }],
      waveform: [],
    });
    await cache.save("cap-1", { calls: [], waveform: [] });
    expect((await cache.get("cap-1"))?.calls).toEqual([]);
  });

  it("knows nothing about a capture it has never seen", async () => {
    expect(await new MemoryAnalysisCache().get("nope")).toBeUndefined();
  });
});
