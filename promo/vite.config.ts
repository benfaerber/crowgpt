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
 * `/` and written to dist/, which is what gets uploaded to cawtalker.org. The
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
 * prevents is a literal `{{labels.count}}` on cawtalker.org, which nothing else
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

export default defineConfig({
  base: isPublic ? "/" : "/promo/",
  plugins: [statsTokens()],
  build: {
    outDir: isPublic ? "dist" : "../fieldserver/src/fieldserver/static/promo",
    emptyOutDir: true,
    rollupOptions: {
      // Two pages, not one: the credits roll is its own document so the front
      // page never loads a hundred kilobytes of attribution nobody asked for.
      input: {
        main: resolve(__dirname, "index.html"),
        credits: resolve(__dirname, "credits.html"),
      },
    },
  },
  server: {
    port: 5174,
  },
});
