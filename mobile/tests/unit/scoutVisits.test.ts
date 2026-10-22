import { describe, expect, it, vi } from "vitest";

import { MemoryScoutVisitRepository } from "../../src/data/MemoryScoutVisitRepository";
import { SqliteScoutVisitRepository } from "../../src/data/SqliteScoutVisitRepository";
import { ScoutVisitSync } from "../../src/sync/ScoutVisitSync";
import { buildMapHtml } from "../../src/ui/map/mapHtml";
import { scoutLayerFromServer } from "../../src/domain/scout";
import type { FieldServerClient } from "../../src/net/FieldServerClient";
import type { ScoutVisit } from "../../src/domain/scoutVisits";
import type { ScoutVisitRepository } from "../../src/data/ScoutVisitRepository";

let n = 0;
const freshName = () => `scout-contract-${n++}.db`;

function visit(uuid: string, overrides: Partial<ScoutVisit> = {}): ScoutVisit {
  return {
    uuid, kind: "target", latitude: 40.67, longitude: -111.94,
    outcome: "nothing", visitedAt: "2026-08-20T13:00:00Z", ...overrides,
  };
}

describe.each([
  ["memory", async (): Promise<ScoutVisitRepository> =>
    new MemoryScoutVisitRepository()],
  ["sqlite", (): Promise<ScoutVisitRepository> =>
    SqliteScoutVisitRepository.open(freshName())],
])("ScoutVisitRepository (%s)", (_name, open) => {
  it("round-trips a visit and is idempotent on uuid", async () => {
    const repo = await open();
    await repo.add(visit("v1", { note: "big cottonwood", outcome: "crows" }));
    await repo.add(visit("v1"));
    const all = await repo.all();
    expect(all).toHaveLength(1);
    expect(all[0]).toMatchObject(
      { uuid: "v1", outcome: "crows", note: "big cottonwood" });
  });

  it("pending, confirmed, forgotten", async () => {
    const repo = await open();
    await repo.add(visit("v1"));
    expect(await repo.pendingSync(10)).toHaveLength(1);
    await repo.markSynced("v1", 7, "2026-08-20T14:00:00Z");
    expect(await repo.pendingSync(10)).toHaveLength(0);
    await repo.forgetServerState();
    expect(await repo.pendingSync(10)).toHaveLength(1);
  });
});

describe("ScoutVisitSync", () => {
  it("pushes pending visits and marks them synced", async () => {
    const repo = new MemoryScoutVisitRepository();
    await repo.add(visit("v1"));
    await repo.add(visit("v2"));
    const addScoutVisit = vi.fn(async () => ({ id: 42 }));
    const sync = new ScoutVisitSync(
      repo, () => ({ addScoutVisit }) as unknown as FieldServerClient);
    const outcome = await sync.run();
    expect(outcome).toEqual({ sent: 2 });
    expect(addScoutVisit).toHaveBeenCalledTimes(2);
    expect(await repo.pendingSync(10)).toHaveLength(0);
  });

  it("reports the error and leaves rows pending on failure", async () => {
    const repo = new MemoryScoutVisitRepository();
    await repo.add(visit("v1"));
    const failing = {
      addScoutVisit: async () => { throw new Error("down"); },
    } as unknown as FieldServerClient;
    const sync = new ScoutVisitSync(repo, () => failing);
    const outcome = await sync.run();
    expect(outcome.sent).toBe(0);
    expect(outcome.error).toBe("down");
    expect(await repo.pendingSync(10)).toHaveLength(1);
  });
});

describe("map html with visits", () => {
  const layer = scoutLayerFromServer({
    targets: [{ rank: 1, lat: 40.67, lon: -111.94, score: 0.5,
                near: "", signals: {} }],
    owls: [],
  });

  it("offers mark buttons on an unvisited target", () => {
    const html = buildMapHtml([], undefined, undefined, undefined, layer, []);
    expect(html).toContain("scout-visit");
    expect(html).toContain("Crows here");
  });

  it("defines visits before the tree layer reads them", () => {
    const html = buildMapHtml([], undefined, undefined,
      [{ latitude: 40.7, longitude: -111.9, heightM: 20, areaM2: 100 }],
      layer, [visit("v1")]);
    expect(html.indexOf("var visits =")).toBeLessThan(
      html.indexOf("stands.forEach"));
    expect(html).toContain('"uuid":"v1"');
  });
});

describe("species filter", () => {
  it("ships the filter control with the predator layer", () => {
    const layer = scoutLayerFromServer({
      targets: [{ rank: 1, lat: 40.6, lon: -111.9, score: 0.4,
                  near: "", signals: {} }],
      owls: [],
      predators: [{ lat: 40.6, lon: -111.9, icon: "owl-icon",
                    species: "Great Horned Owl" }],
      icons: { "owl-icon": "data:image/png;base64,AAAA" },
    } as never);
    const html = buildMapHtml([], undefined, undefined, undefined, layer);
    expect(html).toContain("species-filter");
    expect(html).toContain("speciesOn");
  });
});

describe("crow filter rows", () => {
  it("splits captures by keep and labels community crows", () => {
    const html = buildMapHtml([
      { uuid: "a", latitude: 40.7, longitude: -111.9, keep: true,
        label: "x", detail: "d", color: "#fff" } as never,
    ]);
    expect(html).toContain("★ American Crow — kept capture");
    expect(html).toContain("American Crow — capture");
    expect(html).toContain("' — community'");
    expect(html).toContain("buildSpeciesFilter();");
  });
});

describe("remembered filters", () => {
  it("starts hidden species unchecked and off the map", () => {
    const html = buildMapHtml([], undefined, undefined, undefined, undefined,
      undefined, "keep", ["American Kestrel"]);
    expect(html).toContain('"American Kestrel"');
    expect(html).toContain("hiddenSpecies.indexOf(name) === -1");
    expect(html).toContain("send({ type: 'species-filter'");
  });
});
