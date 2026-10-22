/* End-to-end test of the browser pipeline under Node, on the same WASM engine
 * the page uses. Generates bouts, writes WAVs next to this script, and prints
 * the timing that decides whether the page needs WebGPU or a progress bar.
 *
 *   node node_test.mjs [count] [seed]
 */

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import * as ort from "onnxruntime-web";
import { CrowGpt, seeded, wavBytes } from "./web/crowgpt.js";

const here = fileURLToPath(new URL(".", import.meta.url));
const count = Number(process.argv[2] ?? 3);
const baseSeed = Number(process.argv[3] ?? 30000);

ort.env.wasm.numThreads = 4;

const model = await CrowGpt.load(ort, `${here}web/models`, {
  fetchJson: async (path) => JSON.parse(await readFile(path, "utf8")),
});
console.log(`loaded ${model.config.release}: ` +
  `T=${model.config.sampling.temperature} k=${model.config.sampling.top_k} ` +
  `max_frames=${model.config.sampling.max_frames}`);

for (let i = 0; i < count; i++) {
  const result = await model.generate({ random: seeded(baseSeed + i) });
  const seconds = result.audio.length / model.config.sample_rate;
  const rate = result.steps / result.sampleSeconds;
  console.log(
    `seed ${baseSeed + i}: ${seconds.toFixed(2)} s audio, ` +
    `${result.steps} steps in ${result.sampleSeconds.toFixed(1)} s ` +
    `(${rate.toFixed(0)} tok/s), decode ${result.decodeSeconds.toFixed(1)} s`);
  const path = `${here}node-seed${baseSeed + i}.wav`;
  await writeFile(path, wavBytes(result.audio, model.config.sample_rate));
  console.log(`  wrote ${path}`);
}
