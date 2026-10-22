import { execSync } from "node:child_process";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * What git said when this bundle was built. Same scheme as the phone: the first
 * commit is v1, the hundredth is v100.
 *
 * Baked in rather than fetched, because the question it answers is "is the page
 * I am looking at older than the server serving it?" — and a page cannot ask the
 * server that about itself.
 */
function buildInfo() {
  const git = (args: string, fallback: string) => {
    try {
      return execSync(`git ${args}`, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] })
        .trim();
    } catch {
      return fallback;
    }
  };
  return {
    version: Number.parseInt(git("rev-list --count HEAD", "0"), 10) || 0,
    commit: git("rev-parse --short HEAD", "unknown"),
    committedAt: git("log -1 --format=%cI", "") || undefined,
    dirty: git("status --porcelain", "").length > 0,
  };
}

/**
 * The operator dashboard.
 *
 * Built into `fieldserver/src/fieldserver/static/app/`, which Flask serves — so
 * a production fleet still runs one process on one port and the dashboard is
 * just a URL, not a thing to deploy.
 *
 * In dev, Vite serves it and proxies `/api` to the field server, which keeps hot
 * reload without teaching the Flask app about CORS.
 */
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  define: { __BUILD__: JSON.stringify(buildInfo()) },
  build: {
    outDir: "../fieldserver/src/fieldserver/static/app",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.FIELD_SERVER ?? "http://127.0.0.1:5100",
        changeOrigin: true,
      },
    },
  },
});
