import * as Location from "expo-location";

import { formatRegion } from "../domain/location";
import type { Fix } from "./LocationProvider";

export interface RegionLookup {
  /** "Utah, US" for a fix, or undefined when it cannot be resolved. */
  forFix(fix: Fix): Promise<string | undefined>;
}

/**
 * Which region a fix is in.
 *
 * Deliberately *not* an IP lookup, which is the obvious cheap answer and the
 * wrong one: an address resolves to wherever the ISP registered the block, and
 * this laptop's own connection claims Idaho from Salt Lake City. It also fails
 * completely behind a VPN or carrier NAT, and it would mean telling a third
 * party about every contributor in order to protect their privacy.
 *
 * The phone already has a fix; turning that into a region is a local question.
 * When there is no fix — because the recordist declined GPS, which is exactly
 * the person not to guess about — the answer comes from what they told us in
 * Settings instead.
 */
export class DeviceRegionLookup implements RegionLookup {
  private readonly seen = new Map<string, string | undefined>();

  async forFix(fix: Fix): Promise<string | undefined> {
    // Two decimal places is about a kilometre, which is far finer than a state
    // and keeps a morning of captures down to one lookup.
    const key = `${fix.latitude.toFixed(2)},${fix.longitude.toFixed(2)}`;
    if (this.seen.has(key)) return this.seen.get(key);
    try {
      const [place] = await Location.reverseGeocodeAsync({
        latitude: fix.latitude,
        longitude: fix.longitude,
      });
      const region = place ? formatRegion(place) : undefined;
      this.seen.set(key, region);
      return region;
    } catch {
      // Geocoding needs a network on Android. A capture with no region is
      // still a capture, and the contributor's own answer covers it.
      return undefined;
    }
  }
}
