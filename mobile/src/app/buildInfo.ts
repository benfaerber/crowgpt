import Constants from "expo-constants";

import { UNKNOWN_BUILD, type BuildInfo } from "./buildVersion";

export { formatAge, formatCommitTime, formatVersion, type BuildInfo } from "./buildVersion";

/**
 * The build identity app.config.js resolved from git and stashed in `extra`.
 *
 * Read defensively: `extra` is whatever the manifest happened to contain, and a
 * Settings screen that throws is worse than one that admits it doesn't know.
 */
export function currentBuild(): BuildInfo {
  const extra = Constants.expoConfig?.extra as { build?: Partial<BuildInfo> } | undefined;
  const build = extra?.build;
  if (!build) return UNKNOWN_BUILD;
  return {
    version: build.version ?? 0,
    commit: build.commit ?? "unknown",
    committedAt: build.committedAt,
    dirty: build.dirty ?? false,
    branch: build.branch,
  };
}
