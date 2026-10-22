/**
 * Which build of the dashboard this page is, and which build of the server it
 * is talking to.
 *
 * Two numbers rather than one because they come apart: the bundle is baked at
 * `npm run build` and cached by the browser, the server is whatever process is
 * currently running. A page served from a stale bundle looks exactly like a
 * server that ignored your change.
 */

export interface Build {
  /** Commit count: the first commit is 1, the hundredth is 100. */
  version: number;
  commit: string;
  committedAt?: string;
  dirty: boolean;
}

/**
 * As the server reports it on /api/health — snake_case, straight from Python.
 *
 * The phone declares its own narrower view of this same object as
 * `ServerBuild` in `mobile/src/domain/compatibility.ts`: just `version` and
 * `wire`, because all it does with it is refuse to sync against a server too
 * old to store what it records. The two were disjoint until 2026-07-31 — this
 * one had no `wire` at all — which meant the operator's screen was the one
 * place that could not show the number that decides whether a sync silently
 * drops fields. Now a superset, so a field added here can still be read there.
 */
export interface ServerBuild {
  version: number;
  commit: string;
  committed_at: string | null;
  dirty: boolean;
  branch: string | null;
  /**
   * What the server can store. Compatibility turns on this, never on `version`
   * — which is a commit count, and an earlier check that compared those called
   * a server three tooling commits behind incompatible. Absent on a server too
   * old to say.
   */
  wire?: number;
}

declare const __BUILD__: Build;

/** This bundle. Substituted at build time by vite.config.ts. */
export const BUNDLE: Build = __BUILD__;

/**
 * "v121 · 512e11e" — what to read out when something needs diagnosing.
 *
 * The dirty marker is deliberately loud: a build made from uncommitted edits
 * cannot be reproduced from its hash, so a bug reported against one is a bug
 * reported against nothing.
 */
export function formatBuild(build: { version: number; commit: string; dirty: boolean }): string {
  const version = build.version > 0 ? `v${build.version}` : "unversioned";
  return `${version} · ${build.commit}${build.dirty ? " +local edits" : ""}`;
}

/**
 * Whether the open page is older than the server it is talking to.
 *
 * Only reported when the page is *behind*. Ahead happens routinely during
 * development — Vite serves the working tree while the Flask process was started
 * from an older commit — and flagging it would train the eye to ignore the
 * warning that matters.
 */
export function isStale(server: ServerBuild | undefined): boolean {
  if (!server || server.version === 0 || BUNDLE.version === 0) return false;
  return BUNDLE.version < server.version;
}
