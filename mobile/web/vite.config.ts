import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// The labelling desk in a browser: the phone's own LabelingScreen, from
// ../src, with the three native modules it reaches swapped for web ones.
// Nothing under ../src is forked. What differs is what the screen is handed
// (src/ScanDeskServices.ts) and what these aliases resolve to.
export default defineConfig({
  base: "/label/",
  plugins: [react()],
  resolve: {
    alias: [
      { find: /^react-native$/, replacement: here("./node_modules/react-native-web") },
      { find: /^expo-audio$/, replacement: here("./src/shims/expo-audio.ts") },
      { find: /^expo-crypto$/, replacement: here("./src/shims/expo-crypto.ts") },
    ],
    // ../src sits under mobile/node_modules, which has its own React. Two
    // copies in one page is two sets of hooks.
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: here("../../fieldserver/src/fieldserver/static/label"),
    emptyOutDir: true,
  },
  server: {
    port: 5175,
    fs: { allow: [here("..")] },
    proxy: { "/api": "http://127.0.0.1:5100" },
  },
});
