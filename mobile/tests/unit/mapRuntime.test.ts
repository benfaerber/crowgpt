/**
 * Runs the map page's generated script against a stub Leaflet and DOM.
 *
 * The string-matching tests can't catch a script that throws halfway and
 * silently draws nothing after the error — which is exactly how a layer
 * "disappears" on the phone with no failing test on the laptop.
 */
import { describe, expect, it } from "vitest";

import { scoutLayerFromServer } from "../../src/domain/scout";
import { buildMapHtml } from "../../src/ui/map/mapHtml";

function chainable(): unknown {
  const store: Record<PropertyKey, unknown> = {};
  const fn = () => proxy;
  const proxy: unknown = new Proxy(fn, {
    get: (_t, prop) => {
      if (prop in store) return store[prop];
      if (prop === Symbol.toPrimitive || prop === "toString") return () => "";
      return chainable();
    },
    set: (_t, prop, value) => { store[prop] = value; return true; },
    apply: () => chainable(),
  });
  return proxy;
}

function stubElement(): Record<string, unknown> {
  const el: Record<string, unknown> = {
    children: [] as unknown[],
    style: {},
    classList: { toggle: () => undefined, add: () => undefined },
    appendChild(child: unknown) { (el.children as unknown[]).push(child); return child; },
    addEventListener: () => undefined,
    setAttribute: () => undefined,
    querySelector: () => null,
    remove: () => undefined,
  };
  return el;
}

function runMapScript(html: string) {
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  const pageScript = scripts[scripts.length - 1][1];
  const drawn = { polylines: 0, circles: 0, markers: 0 };
  const markerPopups: unknown[] = [];
  const circlePopups: unknown[] = [];
  const withPopup = (bucket: unknown[]) => {
    const m: Record<string, unknown> = Object.assign(chainable() as object, {
      bindPopup: (content: unknown) => { bucket.push(content); return m; },
      addTo: () => m,
    });
    return m;
  };
  const bounds = { contains: () => true, pad: () => bounds };
  const map = Object.assign(chainable() as object, {
    on: () => map, getZoom: () => 15, getBounds: () => bounds,
    hasLayer: () => false, removeLayer: () => map, addLayer: () => map,
    setView: () => map, fitBounds: () => map, _popup: null,
    // Everything projects to one pixel, so the icon fan-out's collision
    // arithmetic runs against every marker in the test layer.
    latLngToLayerPoint: () => ({ x: 100, y: 100 }),
  });
  const group = () => {
    const g: Record<string, unknown> = Object.assign(chainable() as object, {
      addTo: () => g, addLayer: () => g, removeLayer: () => g,
      clearLayers: () => g,
    });
    return g;
  };
  const L = Object.assign(chainable() as object, {
    map: () => Object.assign(map, {
      attributionControl: { setPrefix: () => undefined },
    }),
    tileLayer: () => chainable(),
    layerGroup: group,
    control: () => {
      const c: Record<string, unknown> = { addTo: () => c };
      return c;
    },
    polyline: () => Object.assign(chainable() as object, {
      addTo: () => { drawn.polylines += 1; return chainable(); },
    }),
    circleMarker: () => { drawn.circles += 1; return withPopup(circlePopups); },
    circle: () => chainable(),
    marker: () => { drawn.markers += 1; return withPopup(markerPopups); },
    divIcon: () => ({}),
    icon: () => ({}),
    DomEvent: { disableClickPropagation: () => undefined,
                disableScrollPropagation: () => undefined },
  });
  const doc = { createElement: stubElement, createTextNode: () => ({}),
                body: stubElement() };
  const win: Record<string, unknown> = {};
  // setTimeout runs synchronously so the gated refreshers execute in-test.
  new Function("L", "document", "window", "setTimeout", pageScript)(
    L, doc, win, (f: () => void) => f());
  // Lazy popups only reveal their content when opened — and only opening
  // them catches the shared-loop-variable bug that titled every sighting
  // on the map "Black-billed Magpie".
  const open = (list: unknown[]) => list
    .map((c) => (typeof c === "function" ? c() : c))
    .filter((c): c is string => typeof c === "string");
  return { drawn, win, iconPopups: open(markerPopups) };
}

const layer = scoutLayerFromServer({
  regions: [{ slug: "slc-valley", name: "Salt Lake Valley" },
            { slug: "davis", name: "Davis County" }],
  targets: [{ rank: 1, lat: 40.67, lon: -111.94, score: 0.5, near: "",
              signals: {}, region: "slc-valley" }],
  owls: [{ lat: 40.77, lon: -111.85, region: "slc-valley" }],
  predators: [{ lat: 40.7, lon: -111.9, icon: "owl-icon",
                species: "Great Horned Owl", region: "davis" },
              { lat: 40.7001, lon: -111.9001, icon: "raven-icon",
                species: "Common Raven", region: "davis" }],
  icons: { "owl-icon": "data:image/png;base64,x",
           "raven-icon": "data:image/png;base64,y" },
  rail: [
    { color: "#004a97", region: "slc-valley",
      coords: [[40.76, -111.9], [40.77, -111.9]] },
    { color: "#a4228e", region: "davis",
      coords: [[41.0, -111.9], [41.01, -111.9]] },
  ],
} as never);

describe("map page script, executed", () => {
  it("draws every rail segment with rail on and all counties visible", () => {
    const { drawn } = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], [], true));
    expect(drawn.polylines).toBe(2);
  });

  it("hidden county and rail-off both thin the lines", () => {
    const hiddenDavis = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], ["davis"], true));
    expect(hiddenDavis.drawn.polylines).toBe(1);
    const railOff = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], [], false));
    expect(railOff.drawn.polylines).toBe(0);
  });

  it("every opened icon popup names its own bird, not the last one drawn", () => {
    // Icon markers only: the canvas dots bind per-row via forEach and were
    // never wrong — mixing them in hid exactly the bug this test is for.
    const { iconPopups } = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], [], true));
    const text = iconPopups.join("\n");
    expect(text).toContain("Great Horned Owl");
    expect(text).toContain("Common Raven");
  });

  it("plants the you-dot from an injected fix alone", () => {
    const { win } = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], [], true));
    expect(typeof win.setPosition).toBe("function");
    (win.setPosition as (a: number, b: number, c: number) => void)(40.7, -111.9, 10);
  });

  it("scout-anywhere spots draw with their own popups", () => {
    const { win, drawn } = runMapScript(buildMapHtml(
      [], undefined, undefined, undefined, layer, [], "keep", [], [], true));
    expect(typeof win.showSpots).toBe("function");
    const before = drawn.markers;
    (win.showSpots as (s: unknown[]) => void)([
      { rank: 1, latitude: 40.61, longitude: -111.82, score: 0.7,
        near: "Somewhere Park", signals: { trees: 0.9 } },
    ]);
    expect(drawn.markers).toBe(before + 1);
  });
});
