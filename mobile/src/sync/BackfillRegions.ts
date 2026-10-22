import { markCaptureDirty } from "../app/Annotations";
import { log } from "../app/Log";
import type { CaptureRepository } from "../data/CaptureRepository";
import type { Fix } from "../recording/LocationProvider";

/**
 * Give captures recorded before the region feature existed a region.
 *
 * Every capture already carries the answer — its own GPS fix — so this is
 * reading what is there rather than inventing anything. Without it a corpus
 * collected over a month reads "no location" on every row while the setting
 * is on, which looks like the feature is broken rather than young.
 *
 * Resolved from the fix, one lookup per square kilometre, and falling back to
 * what the recordist said about themselves for captures that never had one.
 * Each change bumps the revision, so the regions go up with the next sync.
 * The same shape as Restore and PrefetchAnalysis, for the same reason: a
 * one-shot job over the repository, built at call time and thrown away.
 */
export class BackfillRegions {
  constructor(
    private readonly deps: {
      repository: CaptureRepository;
      regionFor: (fix: Fix) => Promise<string | undefined>;
      /** Read at run time — the recordist may have just typed it in Settings. */
      homeRegion: () => string | undefined;
    },
  ) {}

  async run(
    onProgress?: (done: number, total: number) => void,
  ): Promise<{ filled: number; unknown: number }> {
    const home = this.deps.homeRegion();
    const missing = (await this.deps.repository.list()).filter(
      (capture) => !capture.region,
    );
    let filled = 0;
    let unknown = 0;
    let done = 0;
    for (const capture of missing) {
      const region =
        capture.latitude !== undefined && capture.longitude !== undefined
          ? (await this.deps.regionFor({
              latitude: capture.latitude,
              longitude: capture.longitude,
            })) ?? home
          : home;
      if (region) {
        await this.deps.repository.update(capture.uuid, { region });
        // The server has these rows already; without a revision bump the region
        // would sit on the phone and never be sent.
        await markCaptureDirty(this.deps.repository, capture.uuid);
        filled += 1;
      } else {
        unknown += 1;
      }
      done += 1;
      onProgress?.(done, missing.length);
    }
    if (filled > 0) log.info("location", "regions backfilled", { filled, unknown });
    return { filled, unknown };
  }
}
