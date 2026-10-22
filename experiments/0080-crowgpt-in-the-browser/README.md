# 0080 — can CrowGPT run client-side in a browser?

Asked 2026-08-18, prompted by wanting a "generate a crow" button on the promo
page that costs the server nothing. The question splits in two: does the full
pipeline — 21.9M-parameter transformer, KV-cached sampling loop, legality
mask, EnCodec decode through the finetuned decoder — survive the trip to
ONNX + JavaScript bit-faithfully, and is it fast enough to be a demo rather
than a spinner.

## Method

`run.py` exports a release (crowgpt2 by default) as two ONNX graphs:

- `model.onnx` — one cached generation step `(token, position, past) ->
  (logits, grown past)`. The written prefix is a single species token, so
  there is no priming graph; the loop starts from an empty cache. The
  position is an explicit input because the TorchScript tracer bakes Python
  shape arithmetic into constants — deriving it from the past tensor's shape
  would freeze it at the example input's value.
- `decoder.onnx` — EnCodec codes -> waveform through the release's decoder
  (0063's adversarial finetune for crowgpt2).

`web/crowgpt.js` ports `Sampler.tokens()` to ONNX Runtime: mask before
temperature, top-k over the legal slice, EOS only on frame boundaries, prefix
stripped by stated length, trailing partial frame dropped. The same module
runs under Node (`node_test.mjs`, onnxruntime-web's WASM engine — the same
binary the browser runs) and in `web/index.html` (WebGPU where available,
threaded WASM fallback; `serve.py` sends the COOP/COEP headers threads need).

## Results, 2026-08-18

**Parity.** Max |logit diff| torch vs ONNX over 200 cached steps: 4.7e-05.
Max |sample diff| through the decoder: 3.2e-06 against a 1.03 peak. The
browser and Node runs are bit-reproducible with the same seed (seed 30000
gives the identical 2.51 s bout in both).

**Speed, WASM ×4 threads (Ryzen laptop, Node = browser engine):**

| seed | audio | steps | sampling | rate |
|---|---|---|---|---|
| 30000 | 2.51 s | 1507 | 14.4 s* | 105 tok/s |
| 30001 | 1.36 s | 819 | 3.6 s | 225 tok/s |
| 30002 | 0.97 s | 587 | 2.0 s | 288 tok/s |

*first run includes session warm-up. Decode is negligible (≤0.1 s). So WASM
costs roughly 2–6× real time: a bout arrives in seconds, not minutes, and a
progress bar covers it. WebGPU was not measurable headless (no adapter); the
page tries it first and falls back.

**Is it still a crow?** BirdNET on the three Node-generated clips as-is (no
3 s ambience framing, so these read low — see crowgpt/README on judging):
seed 30000 detects as corvid at 0.448 against the 0.25 threshold; the two
sub-1.5 s-ish clips score 0, consistent with the known short-audio caveat.
The JS path produces the same distribution the Python sampler does — parity
above is the real evidence; this is just the end-to-end smoke check.

**Sizes.** model.onnx 87.7 MB + decoder.onnx 34 MB, fp32, plus ~14 MB of
onnxruntime-web. Fine locally; a promo deploy would want fp16/int8
quantisation (expect ~30–45 MB total) — unmeasured here.

## Run it

```bash
cd crowgpt && .venv/bin/python ../experiments/0080-crowgpt-in-the-browser/run.py
cd ../experiments/0080-crowgpt-in-the-browser && npm install
node node_test.mjs 3            # generates WAVs, prints tok/s
python serve.py 8092            # then open http://127.0.0.1:8092/
```

`onnx`/`onnxruntime` were added to the crowgpt venv ad hoc (`uv pip install`,
not in pyproject; `uv sync` removes them). The install bumped protobuf
3.19 -> 7.35; birdnetlib/tflite was re-tested through a real inference and is
unaffected. The exported graphs and vendored runtime are gitignored, like
every other checkpoint in the tree.

## What it changed

The browser is now a proven runtime for CrowGPT: full parity, single-digit
seconds per bout on CPU WASM. "Can we?" is answered; what remains for a promo
deploy is product work (quantise, bundle into `promo/`) and Ben's go-ahead
(FUTURE.txt, "CROWGPT in the browser" entry). Publishing is his call to make,
not a gate for agents to enforce.
