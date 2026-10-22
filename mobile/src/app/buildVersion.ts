/**
 * How a build describes itself. Pure — no expo, no React — so the host test run
 * can import it without dragging the native module graph in behind it.
 */

/** What git said when this bundle was built. See app.config.js. */
export interface BuildInfo {
  /** Commit count: first commit is 1, the hundredth is 100. */
  version: number;
  /** Short hash — the exact commit, when the number alone isn't enough. */
  commit: string;
  /** ISO 8601 commit timestamp, absent if git wasn't available. */
  committedAt?: string;
  /** Built with uncommitted edits, so `commit` doesn't fully describe it. */
  dirty: boolean;
  branch?: string;
}

export const UNKNOWN_BUILD: BuildInfo = { version: 0, commit: "unknown", dirty: false };

/**
 * "v100 · 73c083f" — what to read out when something needs diagnosing.
 *
 * The dirty marker is deliberately loud: a build made from uncommitted edits
 * cannot be reproduced from its hash, so a bug reported against one is a bug
 * reported against nothing.
 */
export function formatVersion(build: BuildInfo): string {
  const version = build.version > 0 ? `v${build.version}` : "unversioned";
  return `${version} · ${build.commit}${build.dirty ? " +local edits" : ""}`;
}

/**
 * "25 Jul 2026, 18:19 (2h ago)" in the phone's own timezone.
 *
 * The commit time, not the build time: the question being asked is "how old is
 * the code on this phone", and an APK assembled today from last week's commit is
 * last week's app.
 */
export function formatCommitTime(build: BuildInfo, now: Date = new Date()): string | undefined {
  const committed = parseCommittedAt(build);
  if (!committed) return undefined;

  const stamp = committed.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${stamp} (${formatAge(committed, now)})`;
}

export function parseCommittedAt(build: BuildInfo): Date | undefined {
  if (!build.committedAt) return undefined;
  const committed = new Date(build.committedAt);
  return Number.isNaN(committed.getTime()) ? undefined : committed;
}

/** How stale the build is — the part that decides "should I reinstall before I go?". */
export function formatAge(committed: Date, now: Date): string {
  const minutes = Math.floor((now.getTime() - committed.getTime()) / 60_000);
  // A phone whose clock is behind the build machine's would otherwise report a
  // negative age, which reads as nonsense rather than as a clock problem.
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}
