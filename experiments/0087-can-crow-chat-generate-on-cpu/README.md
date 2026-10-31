# 0087 — can Crow Chat generate on CPU?

2026-10-30. Asked while deciding whether a hosted field server needs a GPU.
The generate worker samples a bout from a CrowGPT checkpoint and decodes it
through EnCodec; today it runs on the laptop's RTX 4070 Ti SUPER. If a CPU
VPS can do the same job in a tolerable time, the hosted system needs no GPU
at all, since BirdNET here is tflite on CPU and the transcriber stays local.

Not the browser path. 0080's WASM prototype is a different runtime and Ben
judged its audio inferior; this measures the worker's own Python sampler,
same checkpoint, same decoder, same code, with the device switched.

## Method

`run.py <device> <threads> <recipe,...>` loads each recipe exactly as the
worker does (`fieldserver/worker/generate_worker.py` RECIPES, the worker's own
sampling settings) and times three seeded bouts, conditioned on the first
call type where the model takes one. CPU runs set `CUDA_VISIBLE_DEVICES=""`.
Audio is 24 kHz, so samples / 24000 is the clip length.

```bash
cd crowgpt
CUDA_VISIBLE_DEVICES="" .venv/bin/python ../experiments/0087-can-crow-chat-generate-on-cpu/run.py cpu 4 model-longctx-ct-b32,crowgpt2
.venv/bin/python ../experiments/0087-can-crow-chat-generate-on-cpu/run.py cuda 4 model-longctx-ct-b32
```

## Results, 2026-10-30, Ryzen laptop (32 threads), GPU otherwise idle

model-longctx-ct-b32 (the crowgpt3 serving candidate, d512/L12):

| device | threads | load | bout 1 | bout 2 | bout 3 |
|---|---|---|---|---|---|
| cuda | – | 2.3 s | 6.0 s for 4.0 s audio | 8.5 s for 5.3 s | 2.5 s for 2.4 s |
| cpu | 4 | 2.0 s | 20.3 s for 4.5 s audio | 10.5 s for 2.7 s | 17.1 s for 3.9 s |
| cpu | 16 | 1.9 s | 19.8 s for 4.5 s audio | 10.1 s for 2.7 s | 16.3 s for 3.9 s |

crowgpt2 on cpu x4: 9.0 s, 16.6 s, 20.1 s for 2.4 s, 3.9 s, 4.6 s of audio.

Seeds draw differently per device, so the GPU and CPU rows are not the same
bouts; compare the rates. CPU runs at about 4 to 4.5 seconds of wall per
second of audio and the GPU at about 1.5. Threads beyond four buy nothing:
the sampling loop is one token at a time and the matrices are small.

## What it changed

A CPU VPS can serve Crow Chat. A bout takes ten to twenty seconds instead of
three to eight, which a progress indicator covers and a queue absorbs. The
hosted field server therefore needs no GPU, and a cloud GPU for generation is
a latency upgrade to buy later against measured traffic, not a prerequisite.
Four cores per concurrent generation is the sizing figure.
