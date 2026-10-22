import { describe, expect, it } from "vitest";

import { scoutLayerFromServer } from "../../src/domain/scout";
import { buildMapHtml } from "../../src/ui/map/mapHtml";
import { FieldServerClient } from "../../src/net/FieldServerClient";
import type { HttpClient, HttpRequest, HttpResponse } from "../../src/net/HttpClient";

const payload = {
  targets: [{ rank: 1, lat: 40.67, lon: -111.94, score: 0.58,
              near: "Somewhere Park", signals: { inat: 1.0 } }],
  owls: [{ lat: 40.77, lon: -111.85 }],
};

describe("scoutLayerFromServer", () => {
  it("normalises targets and owls, dropping malformed rows", () => {
    const layer = scoutLayerFromServer({
      targets: [...payload.targets, { rank: 2, lat: "x", lon: 0, score: 0 }],
      owls: [...payload.owls, { lat: null }],
    } as never);
    expect(layer.targets).toHaveLength(1);
    expect(layer.targets[0]).toMatchObject(
      { rank: 1, latitude: 40.67, longitude: -111.94, near: "Somewhere Park" });
    expect(layer.owls).toEqual([
      { latitude: 40.77, longitude: -111.85, region: "" }]);
  });

  it("carries region tags and the county list when the layer has them", () => {
    const layer = scoutLayerFromServer({
      regions: [{ slug: "davis", name: "Davis County" }, { slug: 7 }],
      targets: [{ ...payload.targets[0], region: "davis" }],
      owls: [{ ...payload.owls[0], region: "davis" }],
    } as never);
    expect(layer.regions).toEqual([{ slug: "davis", name: "Davis County" }]);
    expect(layer.targets[0].region).toBe("davis");
    expect(layer.owls[0].region).toBe("davis");
  });
});

describe("map html with scout layer", () => {
  it("draws targets and owls when passed", () => {
    const html = buildMapHtml([], undefined, undefined, undefined,
      scoutLayerFromServer(payload));
    expect(html).toContain('"rank":1');
    expect(html).toContain("Great Horned Owl");
  });

  it("stays empty without the layer", () => {
    expect(buildMapHtml([])).toContain('"targets":[]');
  });

  it("ships the county filter and remembered settings into the page", () => {
    const html = buildMapHtml([], undefined, undefined, undefined,
      scoutLayerFromServer({
        ...payload,
        regions: [{ slug: "slc-valley", name: "Salt Lake Valley" },
                  { slug: "davis", name: "Davis County" }],
      } as never),
      undefined, "keep", [], ["davis"], false);
    expect(html).toContain("Davis County");
    expect(html).toContain('var hiddenRegions = ["davis"]');
    expect(html).toContain("var railOn = false");
  });
});

class FakeServer implements HttpClient {
  constructor(private readonly status: number, private readonly body: string) {}

  async send(request: HttpRequest): Promise<HttpResponse> {
    if (request.url.endsWith("/api/scout")) {
      return { status: this.status, body: this.body };
    }
    throw new Error(`unexpected ${request.url}`);
  }

  async sendBytes(): Promise<HttpResponse> {
    throw new Error("not used");
  }
}

describe("FieldServerClient.scout", () => {
  it("returns the layer when published", async () => {
    const client = new FieldServerClient(
      "http://server", new FakeServer(200, JSON.stringify(payload)));
    const got = await client.scout();
    expect(got?.targets).toHaveLength(1);
  });

  it("treats 404 as no layer", async () => {
    const client = new FieldServerClient(
      "http://server", new FakeServer(404, "not found"));
    expect(await client.scout()).toBeNull();
  });
});

describe("predator icons", () => {
  const withPredators = scoutLayerFromServer({
    targets: [{ rank: 1, lat: 40.67, lon: -111.94, score: 0.5,
                near: "", signals: {} }],
    owls: [{ lat: 40.77, lon: -111.85 }],
    predators: [
      { lat: 40.78, lon: -111.86, icon: "great-horned-owl-icon",
        species: "Great Horned Owl" },
      { lat: "bad", lon: 0, icon: 3 },
    ],
    icons: { "great-horned-owl-icon": "data:image/png;base64,AAAA",
             evil: "javascript:alert(1)" },
  } as never);

  it("normalises predators and refuses non-data-URI icons", () => {
    expect(withPredators.predators).toHaveLength(1);
    expect(Object.keys(withPredators.icons)).toEqual(["great-horned-owl-icon"]);
  });

  it("draws predators with their icons instead of the owl dots", () => {
    const html = buildMapHtml([], undefined, undefined, undefined, withPredators);
    expect(html).toContain("Great Horned Owl");
    expect(html).toContain("data:image/png;base64,AAAA");
  });
});
