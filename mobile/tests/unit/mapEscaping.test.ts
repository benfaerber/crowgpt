import { describe, expect, it } from "vitest";

import { buildMapHtml, type MappedCapture } from "../../src/ui/map/mapHtml";

/**
 * The map is a WebView, and everything in it is built by string concatenation.
 *
 * A family name is free text the recordist typed, and it reaches the page twice
 * — once as JSON inside a `<script>` block, once as HTML inside a popup. Both
 * used to be unescaped, which made a crow family called `</script>` enough to
 * run script with the `postMessage` bridge in reach.
 *
 * The two defences are tested differently on purpose. The JSON escaping happens
 * here, so it is visible in the emitted document and asserted directly. The
 * popup escaping happens in the WebView at render time, so nothing about it
 * shows up in this string — the most an offline test can check is that the
 * emitted script routes the user-supplied fields through `esc`.
 */
function pin(patch: Partial<MappedCapture> = {}): MappedCapture {
  return {
    uuid: "c1",
    latitude: 51.5,
    longitude: -0.1,
    label: "Jul 26, 09:00",
    detail: "3s · synced",
    color: "#6bd28a",
    ...patch,
  };
}

describe("map data cannot break out of the script block", () => {
  it("never lets a family name close the script tag", () => {
    const html = buildMapHtml([pin({ familyName: "</script><img src=x onerror=alert(1)>" })]);

    // Leaflet's bundle and the map's own block contribute one </script> each,
    // and nothing the recordist typed may add a third.
    expect(html.match(/<\/script>/g)).toHaveLength(2);
    expect(html).toContain("\\u003c/script\\u003e");
  });

  it("escapes U+2028, which is legal in JSON and a line break in a script", () => {
    const html = buildMapHtml([pin({ familyName: "a\u2028b" })]);

    expect(html).not.toContain("a\u2028b");
    expect(html).toContain("a\\u2028b");
  });

  it("escapes a quote in a colour, so it cannot close a style attribute", () => {
    const html = buildMapHtml([pin({ glow: '#fff" onload="alert(1)' })]);

    expect(html).not.toContain('onload="alert(1)');
  });

  it("still carries an ordinary family name through", () => {
    const html = buildMapHtml([pin({ familyName: "The Poe Family" })]);

    expect(html).toContain("The Poe Family");
  });
});

describe("popup markup is escaped at render time", () => {
  const html = buildMapHtml([pin({ familyName: "The Poe Family" })]);
  const popup = html.slice(html.indexOf("marker.bindPopup"));

  it.each(["capture.label", "capture.detail", "capture.familyName", "capture.uuid"])(
    "wraps %s in esc()",
    (field) => {
      expect(popup).toContain(`esc(${field})`);
      // The bare field must not also be concatenated in unescaped.
      expect(popup).not.toMatch(new RegExp(`\\+\\s*${field.replace(".", "\\.")}\\b`));
    },
  );

  it("escapes the family colour on its way into the halo", () => {
    // Family mode re-interpolates the family colour; it must pass through
    // esc, and the keep-mode colours stay literals.
    expect(html).toContain("esc(capture.glow || ");
    expect(html).toContain("capture.keep ? '#ffd970'");
  });
});
