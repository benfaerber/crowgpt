import { describe, expect, it } from "vitest";

import { formatRegion } from "../../src/domain/location";
import {
  REGION_GROUPS,
  allRegionKeys,
  regionKey,
  searchRegions,
} from "../../src/domain/regions";

/**
 * The region is a grouping key, not a caption.
 *
 * It decides which captures count as the same population, which is why it is
 * chosen from a list: free text produces "Utah", "utah", "UT" and "Utah, USA"
 * as four different places inside a month, and nothing downstream can put them
 * back together.
 */
describe("the region list", () => {
  it("covers the places this project actually recruits in", () => {
    const keys = allRegionKeys();
    expect(keys).toContain("Utah, US");
    // The hooded crow contributor.
    expect(keys).toContain("Nordrhein-Westfalen, DE");
    expect(keys).toContain("Ontario, CA");
  });

  it("stores the same shape a GPS fix produces", () => {
    // Otherwise a capture placed by its fix and one placed by its owner's
    // answer would be two populations rather than one.
    expect(regionKey("Utah", "US")).toBe(
      formatRegion({ region: "Utah", isoCountryCode: "US" }),
    );
  });

  it("has no duplicates to split a population across", () => {
    const keys = allRegionKeys();
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("names every group with a country code the key can end in", () => {
    for (const group of REGION_GROUPS) {
      expect(group.country).toMatch(/^[A-Z]{2}$/);
      expect(group.regions.length).toBeGreaterThan(0);
    }
  });
});

describe("searching it", () => {
  it("finds a state by its own name", () => {
    expect(searchRegions("utah").map((m) => m.key)).toEqual(["Utah, US"]);
  });

  it("finds every region of a country by the country's name", () => {
    // Someone who knows they are in Germany does not necessarily know how this
    // list spells their Bundesland.
    const found = searchRegions("germany").map((m) => m.key);
    expect(found).toContain("Bayern, DE");
    expect(found.length).toBe(16);
  });

  it("returns everything when nothing has been typed", () => {
    expect(searchRegions("").length).toBe(allRegionKeys().length);
  });

  it("finds nothing rather than guessing", () => {
    expect(searchRegions("atlantis")).toEqual([]);
  });
});
