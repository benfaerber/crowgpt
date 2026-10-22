/* The sampling loop from crowgpt/sample.py, ported to ONNX Runtime.
 *
 * Engine-agnostic on purpose: the caller hands in the `ort` namespace, so the
 * same module runs under onnxruntime-web in a browser and under Node for the
 * automated test. Mirrors Sampler.tokens(): legality mask, temperature after
 * the mask, top-k over the legal slice, EOS only on frame boundaries, prefix
 * stripped by stated length, trailing partial frame dropped.
 */

export class CrowGpt {
  constructor(ort, config, stepSession, decoderSession) {
    this.ort = ort;
    this.config = config;
    this.step = stepSession;
    this.decoder = decoderSession;
  }

  static async load(ort, baseUrl, options = {}) {
    const fetchJson = options.fetchJson ??
      (async (url) => (await fetch(url)).json());
    const config = await fetchJson(`${baseUrl}/config.json`);
    const sessionOptions = options.sessionOptions ?? {};
    const step = await ort.InferenceSession.create(
      `${baseUrl}/model.onnx`, sessionOptions);
    const decoder = await ort.InferenceSession.create(
      `${baseUrl}/decoder.onnx`, sessionOptions);
    return new CrowGpt(ort, config, step, decoder);
  }

  /* [start, end) of legal ids at an absolute position, plus EOS legality. */
  legalAt(position) {
    const c = this.config;
    if (position < c.prefix_len) {
      const [start, end] = c.prefix_slots[position];
      return { start, end, eos: false };
    }
    const stage = (position - c.prefix_len) % c.n_codebooks;
    return {
      start: stage * c.codebook_size,
      end: (stage + 1) * c.codebook_size,
      eos: stage === 0,
    };
  }

  /* One draw: mask, temperature, top-k, softmax, sample. */
  draw(logits, position, temperature, topK, random) {
    const { start, end, eos } = this.legalAt(position);
    const ids = [];
    for (let id = start; id < end; id++) ids.push(id);
    if (eos) ids.push(this.config.eos);
    const scored = ids.map((id) => ({ id, score: logits[id] / temperature }));
    scored.sort((a, b) => b.score - a.score);
    const kept = topK ? scored.slice(0, Math.min(topK, scored.length)) : scored;
    const peak = kept[0].score;
    let total = 0;
    for (const entry of kept) {
      entry.weight = Math.exp(entry.score - peak);
      total += entry.weight;
    }
    let roll = random() * total;
    for (const entry of kept) {
      roll -= entry.weight;
      if (roll <= 0) return entry.id;
    }
    return kept[kept.length - 1].id;
  }

  emptyPast() {
    const c = this.config;
    return new this.ort.Tensor(
      "float32", new Float32Array(0), [c.n_layer, c.n_head, 0, c.head_dim]);
  }

  /* Generate flat codec tokens for one bout. Returns { tokens, steps }. */
  async tokens({ species, temperature, topK, maxFrames, random = Math.random,
                 onStep = null } = {}) {
    const c = this.config;
    temperature ??= c.sampling.temperature;
    topK ??= c.sampling.top_k;
    maxFrames ??= c.sampling.max_frames;
    const slug = species ?? c.default_species;
    const index = c.species.indexOf(slug);
    if (index < 0) throw new Error(`unknown species ${slug}`);

    const limit = Math.min(c.block_size, c.prefix_len + maxFrames * c.n_codebooks);
    const sequence = [c.species_base + index];
    let pastK = this.emptyPast();
    let pastV = this.emptyPast();
    let logits = null;
    let steps = 0;

    while (sequence.length < limit) {
      const position = sequence.length - 1;
      const fed = sequence[position];
      const out = await this.step.run({
        token: new this.ort.Tensor(
          "int64", BigInt64Array.from([BigInt(fed)]), [1, 1]),
        position: new this.ort.Tensor(
          "int64", BigInt64Array.from([BigInt(position)]), [1]),
        past_k: pastK,
        past_v: pastV,
      });
      pastK = out.new_k;
      pastV = out.new_v;
      logits = out.logits.data;
      steps += 1;

      const next = this.draw(logits, sequence.length, temperature, topK, random);
      if (next === c.eos) break;
      sequence.push(next);
      if (onStep && steps % 16 === 0) await onStep(steps, limit - c.prefix_len);
    }

    const flat = sequence.slice(c.prefix_len);
    const usable = Math.floor(flat.length / c.n_codebooks) * c.n_codebooks;
    return { tokens: flat.slice(0, usable), steps };
  }

  /* Flat tokens -> [K, frames] codes -> waveform Float32Array. */
  async decode(tokens) {
    const c = this.config;
    const frames = tokens.length / c.n_codebooks;
    const codes = new BigInt64Array(tokens.length);
    for (let t = 0; t < frames; t++) {
      for (let k = 0; k < c.n_codebooks; k++) {
        codes[k * frames + t] =
          BigInt(tokens[t * c.n_codebooks + k] - k * c.codebook_size);
      }
    }
    const out = await this.decoder.run({
      codes: new this.ort.Tensor("int64", codes, [1, c.n_codebooks, frames]),
    });
    return Float32Array.from(out.audio.data);
  }

  async generate(options = {}) {
    const began = now();
    const { tokens, steps } = await this.tokens(options);
    const sampled = now();
    if (tokens.length === 0) {
      return { audio: new Float32Array(0), tokens, steps,
               sampleSeconds: (sampled - began) / 1000, decodeSeconds: 0 };
    }
    const audio = await this.decode(tokens);
    return {
      audio, tokens, steps,
      sampleSeconds: (sampled - began) / 1000,
      decodeSeconds: (now() - sampled) / 1000,
    };
  }
}

function now() {
  return (typeof performance !== "undefined" ? performance : Date).now();
}

/* Deterministic RNG for seeded generation (mulberry32). */
export function seeded(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* Float32 [-1, 1] -> 16-bit PCM WAV bytes. */
export function wavBytes(audio, sampleRate) {
  const data = new DataView(new ArrayBuffer(44 + audio.length * 2));
  const text = (offset, s) => {
    for (let i = 0; i < s.length; i++) data.setUint8(offset + i, s.charCodeAt(i));
  };
  text(0, "RIFF");
  data.setUint32(4, 36 + audio.length * 2, true);
  text(8, "WAVEfmt ");
  data.setUint32(16, 16, true);
  data.setUint16(20, 1, true);
  data.setUint16(22, 1, true);
  data.setUint32(24, sampleRate, true);
  data.setUint32(28, sampleRate * 2, true);
  data.setUint16(32, 2, true);
  data.setUint16(34, 16, true);
  text(36, "data");
  data.setUint32(40, audio.length * 2, true);
  for (let i = 0; i < audio.length; i++) {
    const clamped = Math.max(-1, Math.min(1, audio[i]));
    data.setInt16(44 + i * 2, Math.round(clamped * 32767), true);
  }
  return new Uint8Array(data.buffer);
}
