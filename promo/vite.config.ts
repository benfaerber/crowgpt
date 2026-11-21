import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig, type Plugin } from "vite";

/**
 * The promo site, which has two homes.
 *
 * By default it builds into the field server's static/, where it is served at
 * /promo — one process on one port for a running fleet.
 *
 * `PROMO_PUBLIC=1` builds the same page for the public host instead: rooted at
 * `/` and written to dist/, which is what gets uploaded to crowgpt.org. The
 * base path is the whole difference, and it has to be decided at build time
 * because Vite bakes asset URLs into the HTML.
 */
const isPublic = process.env.PROMO_PUBLIC === "1";

const STATS = resolve(__dirname, "stats.json");

/**
 * Substitutes `{{key}}` in the HTML with the matching figure's text from
 * stats.json, at build time.
 *
 * Build time, not runtime, on purpose: the served HTML carries real numbers, so
 * a reader with no JavaScript, a view-source, and a link preview all see the
 * same figures the page does — and the bundle still reads no store and takes no
 * token. `promo/tools/build_stats.py` is what puts current numbers in the file.
 *
 * An unknown key is a build error rather than a fallback. The failure this
 * prevents is a literal `{{labels.count}}` on crowgpt.org, which nothing else
 * here would catch.
 */
function statsTokens(): Plugin {
  return {
    name: "promo-stats-tokens",
    transformIndexHtml: {
      order: "pre",
      handler(html, context) {
        const figures = JSON.parse(readFileSync(STATS, "utf8")).figures as Record<
          string,
          { text: string }
        >;
        return html.replace(/\{\{\s*([a-z0-9_.]+)\s*\}\}/gi, (_match, key: string) => {
          const figure = figures[key];
          if (!figure) {
            throw new Error(
              `${context.filename}: no figure "${key}" in promo/stats.json. ` +
                `Known keys: ${Object.keys(figures).join(", ")}`,
            );
          }
          return figure.text;
        });
      },
    },
    configureServer(server) {
      // The dev server has the HTML cached with the old numbers baked in, so
      // editing stats.json otherwise looks like it did nothing.
      server.watcher.add(STATS);
      server.watcher.on("change", (path) => {
        if (path === STATS) server.ws.send({ type: "full-reload" });
      });
    },
  };
}

/**
 * Where the live CrowGPT buttons send a visitor's press. The field server
 * serves the /promo build itself, so that one calls its own origin; the
 * public build names the hosted API. This is the only thing on the page that
 * talks to a server; its Turnstile token is verified there — see src/live-caw.ts.
 */
const FIELD_API = isPublic ? "https://field.crowgpt.org" : "";

/**
 * Where the Scan page asks for the visitor's approximate location. On
 * crowgpt.org that is the site's own /geo (worker/geo.js). The copy a field
 * server serves has no such route, so it asks nobody; `scan.html?near=lat,lon`
 * stands in for it there.
 */
const GEO_URL = isPublic ? "/geo" : "";

export default defineConfig({
  base: isPublic ? "/" : "/promo/",
  plugins: [statsTokens()],
  define: {
    __FIELD_API__: JSON.stringify(FIELD_API),
    __GEO_URL__: JSON.stringify(GEO_URL),
  },
  build: {
    outDir: isPublic ? "dist" : "../fieldserver/src/fieldserver/static/promo",
    emptyOutDir: true,
    rollupOptions: {
      // Several pages, not one: the credits roll is its own document so the front
      // page never loads a hundred kilobytes of attribution nobody asked for.
      input: {
        main: resolve(__dirname, "index.html"),
        credits: resolve(__dirname, "credits.html"),
        // The scanner is the first section to become its own page: it is a
        // tool people come back to, and the front page is long enough.
        scan: resolve(__dirname, "scan.html"),
        // CrowGPT's own page, so generating has room to be a conversation.
        crowgpt: resolve(__dirname, "crowgpt.html"),
        // The front page is the pitch; the long reads each have their own page,
        // and the front keeps a short teaser for each under the old anchor.
        crows: resolve(__dirname, "crows.html"),
        app: resolve(__dirname, "app.html"),
        cawscout: resolve(__dirname, "cawscout.html"),
        cawdex: resolve(__dirname, "cawdex.html"),
      },
    },
  },
  server: {
    port: 5174,
    // The dev page calls its own origin like the /promo build does, and the
    // local field server answers.
    proxy: {
      "/api": "http://127.0.0.1:5100",
    },
  },
});
