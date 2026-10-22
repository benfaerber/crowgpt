import * as Location from "expo-location";

import { withTimeout } from "../domain/timeout";

export interface Fix {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
}

export interface LocationProvider {
  /** A fix, or undefined if permission was refused or nothing could be obtained. */
  current(): Promise<Fix | undefined>;
  /**
   * Live compass heading in degrees clockwise from north; resolves to an
   * unsubscribe. Optional so fakes without a magnetometer stay small.
   */
  watchHeading?(onHeading: (degrees: number) => void): Promise<() => void>;
  /** Live position stream for the map's you-dot; resolves to an unsubscribe. */
  watchPosition?(onFix: (fix: Fix) => void): Promise<() => void>;
}

/**
 * How long to wait for a fix before recording the capture without one.
 *
 * There has to be a number here at all, which was the bug: `getCurrentPositionAsync`
 * has no timeout and does not resolve indoors or under heavy cover. Stopping a
 * recording awaited it from inside the recorder's mutual-exclusion guard, so a
 * fix that never arrived left the earbud button dead for the rest of the
 * session — the recording stopped, the tone played, and every press after that
 * was silently dropped.
 *
 * Fifteen seconds because a Balanced fix outdoors is normally two or three, and
 * anything still trying after fifteen is not about to succeed.
 */
export const FIX_TIMEOUT_MS = 15_000;

/**
 * GPS for a capture.
 *
 * Location never blocks recording: a capture with no fix is still a capture,
 * and losing the audio because the sky was obstructed would be the worse
 * trade. Failures resolve to `undefined` rather than throwing — and so does
 * taking too long, which is the same thing from the caller's point of view and
 * used not to be.
 */
export class DeviceLocationProvider implements LocationProvider {
  private permissionGranted?: boolean;

  constructor(private readonly timeoutMs = FIX_TIMEOUT_MS) {}

  private async ensurePermission(): Promise<boolean> {
    if (this.permissionGranted === undefined) {
      const status = await withTimeout(
        Location.requestForegroundPermissionsAsync().then((r) => r.status),
        this.timeoutMs,
        undefined,
      );
      // Left undecided rather than remembered as refused: an unanswered
      // dialog is not a "no", and caching it as one would silence GPS for
      // the rest of the install.
      if (status !== "granted") return false;
      this.permissionGranted = true;
    }
    return this.permissionGranted;
  }

  async current(): Promise<Fix | undefined> {
    try {
      if (!(await this.ensurePermission())) return undefined;

      const position = await withTimeout(
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
        this.timeoutMs,
        undefined,
      );
      if (!position) return undefined;
      return {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracyMeters: position.coords.accuracy ?? undefined,
      };
    } catch {
      return undefined;
    }
  }

  async watchHeading(onHeading: (degrees: number) => void): Promise<() => void> {
    try {
      const subscription = await Location.watchHeadingAsync((heading) => {
        // trueHeading is -1 where declination is unavailable; magnetic north
        // is a fine compass for a person orienting a map.
        const degrees =
          heading.trueHeading >= 0 ? heading.trueHeading : heading.magHeading;
        if (degrees >= 0) onHeading(degrees);
      });
      return () => subscription.remove();
    } catch {
      return () => {};
    }
  }

  async watchPosition(onFix: (fix: Fix) => void): Promise<() => void> {
    try {
      if (!(await this.ensurePermission())) return () => {};
      const subscription = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.Balanced,
          timeInterval: 3_000,
          distanceInterval: 5,
        },
        (position) =>
          onFix({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracyMeters: position.coords.accuracy ?? undefined,
          }),
      );
      return () => subscription.remove();
    } catch {
      return () => {};
    }
  }
}
