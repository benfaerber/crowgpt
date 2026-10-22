import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      // The Sqlite* repositories run against real SQL on the host — node's
      // SQLite behind expo-sqlite's method names. This is what lets the
      // contract tests hold the Sqlite and Memory implementations to the
      // same behaviour instead of testing only the fakes.
      "expo-sqlite": fileURLToPath(
        new URL("./tests/support/expoSqliteShim.ts", import.meta.url),
      ),
    },
  },
  test: {
    // Only `tests/unit/` — everything under it runs on the host with no device,
    // no Metro and no native modules. tests/FakeFieldServer.ts lives one level
    // up because it is a helper, not a suite.
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
    // node:sqlite backs the expo-sqlite shim; on Node 22 it still sits
    // behind this flag (unflagged from 23.4, where it is accepted and
    // ignored). Set here so a plain `npx vitest` works on either.
    execArgv: ["--experimental-sqlite"],
  },
});
