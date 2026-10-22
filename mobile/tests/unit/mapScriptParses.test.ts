import { describe, expect, it } from "vitest";

import { buildMapHtml } from "../../src/ui/map/mapHtml";
import { scoutLayerFromServer } from "../../src/domain/scout";

/**
 * The page's own script must parse, or the map is a blank WebView with no
 * error anywhere the operator can see — which is exactly how it failed once.
 * Leaflet's dist is skipped; the last <script> block is ours.
 */
describe("map page script", () => {
  it("parses with every layer populated", () => {
    const html = buildMapHtml(
      [{
        uuid: "u1", latitude: 40.7, longitude: -111.9, label: "Test",
        detail: "d", color: "#fff", glow: undefined, familyName: undefined,
      } as never],
      "u1",
      { latitude: 40.7, longitude: -111.9, accuracyMeters: 5 } as never,
      [{ latitude: 40.71, longitude: -111.91, heightM: 25, areaM2: 500 }],
      scoutLayerFromServer({
        targets: [{ rank: 1, lat: 40.72, lon: -111.92, score: 0.5,
                    near: "O'Neil Park <script>", signals: { inat: 0.5 } }],
        owls: [{ lat: 40.73, lon: -111.93 }],
      }),
      [{ uuid: "v1", kind: "target", latitude: 40.72, longitude: -111.92,
         outcome: "nothing", visitedAt: "2026-08-20T13:00:00Z" }],
    );
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    const page = scripts[scripts.length - 1][1];
    expect(() => new Function(page)).not.toThrow();
  });

  it("parses with everything empty", () => {
    const html = buildMapHtml([]);
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    const page = scripts[scripts.length - 1][1];
    expect(() => new Function(page)).not.toThrow();
  });
});

describe("initialisation order", () => {
  it("defines the gating registry before the tree layer pushes into it", () => {
    const html = buildMapHtml([], undefined, undefined,
      [{ latitude: 40.7, longitude: -111.9, heightM: 20, areaM2: 100 }]);
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    const page = scripts[scripts.length - 1][1];
    expect(page.indexOf("var gatedRefreshers = []")).toBeGreaterThan(-1);
    expect(page.indexOf("var gatedRefreshers = []")).toBeLessThan(
      page.indexOf("gatedRefreshers.push"));
    expect(page.indexOf("var speciesDots = {}")).toBeLessThan(
      page.indexOf("markerGroup("));
  });
});
