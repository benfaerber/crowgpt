import { describe, expect, it } from "vitest";

import { treeColor, treeLayerFromGeojson } from "../../src/domain/trees";
import { buildMapHtml } from "../../src/ui/map/mapHtml";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";

function feature(h: number, lon = -111.9, lat = 40.76) {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { h, area_m2: 400 },
  };
}

describe("treeLayerFromGeojson", () => {
  it("normalises points and drops malformed features", () => {
    const layer = treeLayerFromGeojson({
      features: [
        feature(24),
        { geometry: { type: "Point" }, properties: { h: 30 } },
        { geometry: { type: "Point", coordinates: [1, 2] }, properties: {} },
      ],
    } as never);
    expect(layer.stands).toEqual([
      { longitude: -111.9, latitude: 40.76, heightM: 24, areaM2: 400 },
    ]);
  });

  it("keeps the 0083 colour ramp", () => {
    expect(treeColor(18)).toBe("#f9a825");
    expect(treeColor(21)).toBe("#e64a19");
    expect(treeColor(25)).toBe("#c2185b");
    expect(treeColor(30)).toBe("#7b1fa2");
  });
});

describe("map html with trees", () => {
  it("draws stands without adding them to the bounds", () => {
    const html = buildMapHtml([], undefined, undefined, [
      { latitude: 40.76, longitude: -111.9, heightM: 25, areaM2: 400 },
    ]);
    expect(html).toContain('"heightM":25');
    // Stands render before bounds are collected, so an empty capture list
    // still reads as "no captures", not as a map framed on trees.
    expect(html.indexOf("stands.forEach")).toBeLessThan(
      html.indexOf("var bounds = []"),
    );
  });

  it("omits the layer entirely when no stands are passed", () => {
    expect(buildMapHtml([])).toContain("var stands = []");
  });
});

class FakeServer implements HttpClient {
  constructor(private readonly status: number, private readonly body: string) {}

  async send(request: HttpRequest): Promise<HttpResponse> {
    if (request.url.endsWith("/api/trees")) {
      return { status: this.status, body: this.body };
    }
    throw new Error(`unexpected ${request.url}`);
  }

  async sendBytes(): Promise<HttpResponse> {
    throw new Error("not used");
  }
}

describe("FieldServerClient.trees", () => {
  it("returns the collection when published", async () => {
    const client = new FieldServerClient(
      "http://server", new FakeServer(200, JSON.stringify({ features: [feature(20)] })),
    );
    const payload = await client.trees();
    expect(payload?.features).toHaveLength(1);
  });

  it("treats 404 as no layer, not an error", async () => {
    const client = new FieldServerClient(
      "http://server", new FakeServer(404, "not found"),
    );
    expect(await client.trees()).toBeNull();
  });
});
