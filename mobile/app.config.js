const { execSync } = require("node:child_process");

/**
 * Build identity, resolved from git when the config is evaluated.
 *
 * Which build is on the phone is otherwise unanswerable in the field. "Did I
 * install the fix before I left?" has to be checkable on the handset itself,
 * without a laptop — a real field session was already lost to a build that
 * turned out to be the wrong one.
 *
 * The number is the commit count, so the first commit is 1 and the hundredth is
 * 100. It rises by one per commit, which makes "newer than" a comparison you can
 * do in your head — a hash cannot be ordered by eye, and a semver would have to
 * be remembered and bumped by hand.
 *
 * `expo prebuild` runs on every install and android/ is gitignored, so this is
 * re-read for each build rather than baked in once.
 */
function git(args, fallback) {
  try {
    return execSync(`git ${args}`, {
      cwd: __dirname,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    // A tarball export, or a build box without git. A version that says
    // "unknown" is honest; one that says 0 looks like a real answer.
    return fallback;
  }
}

function buildInfo() {
  return {
    version: Number.parseInt(git("rev-list --count HEAD", "0"), 10) || 0,
    commit: git("rev-parse --short HEAD", "unknown"),
    committedAt: git("log -1 --format=%cI", "") || undefined,
    // Built from edits that are in no commit, so the hash above does not fully
    // describe what is running.
    dirty: git("status --porcelain", "").length > 0,
    branch: git("rev-parse --abbrev-ref HEAD", "") || undefined,
  };
}

module.exports = ({ config }) => {
  const build = buildInfo();
  return {
    ...config,
    extra: { ...config.extra, build },
    android: {
      ...config.android,
      // Android refuses to install an APK whose versionCode is lower than the
      // installed one, which is exactly the guard we want: `make install` can
      // never silently put an older build back on the phone.
      versionCode: Math.max(1, build.version),
    },
  };
};
