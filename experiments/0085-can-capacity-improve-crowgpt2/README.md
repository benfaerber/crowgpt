# 0085 — can capacity improve CrowGPT2?

2026-09-09. CrowGPT3 candidate requested by Ben, with overnight GPU use.
Status: completed successfully 2026-09-10 00:15 MDT. Instrument screen failed.

CrowGPT2 has a useful six-second window, but still produces breathy and
inconsistent voices. The nine-second rung regressed (0079), and effective
batch 32 regressed on this unconditioned stream (0080). Capacity has not
been cleanly tested on this recipe. This candidate increases width from
384 to 512 and depth from 8 to 12, retaining four attention heads.
It tests combined width/depth capacity, not either axis independently.

The rest stays fixed: existing tokens-6s and grouped splits, eight EnCodec
codebooks, species + unit-count + duration prefix, no call-type labels,
dropout zero, 30,000 optimizer steps, AdamW peak LR 0.0003, 200-step warmup,
cosine floor 0.1, seed 0. Effective batch eight is implemented as 4 × 2
accumulation to leave memory headroom. Accumulation preserves example count
but averages micro-batch token means; variable lengths mean this is not
bit-identical to a single eight-example token mean. This is a candidate
screen, not a perfectly isolated causal estimate of capacity.

The longest sequences must pass three full optimizer updates, including
Adam state allocation, before training. Preflight weights are discarded.
CUDA is required; there is no CPU fallback. Training reports every 25 steps
through crowgpt.progress.Run and saves the best validation checkpoint.
The output is crowgpt/results/model-crowgpt3-candidate-0085; recipe.json
records configuration, parameter count, manifest hash and launch revision.
Existing checkpoints are never overwritten by a rerun of this experiment.

## Predictions and gate, before results

Prediction: capacity lowers held-out loss and helps sustain coherent crow
voices across the six-second window. A null or regression is useful evidence
against spending another night simply scaling this recipe.

Screen with 100 gradeable draws per arm at identical T=1.1, k=200,
460-frame cap, finetuned decoder, fresh seeds starting at 85000; reference
is 200 held-out real six-second bouts. Report units/bout, gaps/clip, single
share, median gap and dust rate. Retain every attempted seed and duration,
raw units/gaps and pitch strengths, including the count of rejected short
outputs. The first 12 attempts per arm are saved without quality selection
under crowgpt/results/diagnostics-0085 for labelled diagnostics.

A provisional instrument pass requires best val at least 0.05 below 4.686,
no loss of more than 0.3 units or gaps per clip against freshly drawn
CrowGPT2, and no dust increase above 0.05 absolute. These are screening
margins, not significance claims. Evaluation losses are stochastic and the
micro-batches differ; close results need fixed-example rescoring. The voice
still requires a blinded listening pool before any release decision; audio
diagnostics are not a statistical listening sitting. No release is changed.

## Running and status

From the repo root:

    crowgpt/.venv/bin/python experiments/0085-can-capacity-improve-crowgpt2/run.py

Runs as user service crowgpt-candidate-0085 with an 8.5-hour runtime ceiling.
Logs: journalctl --user -u crowgpt-candidate-0085. Training progress is in
Training on the dashboard (data/progress/0085-crowgpt3-candidate.json).
Validation writes results.json beside this README. A timeout leaves the last
best checkpoint intact but may interrupt validation; check service status
if progress becomes stale. No emails or external publication are performed.

## Results

Finished at 00:15 MDT, 83 minutes total: 64 minutes training and 19 minutes
validation. Early stopping fired at step 22,000 after 8,000 steps without
improving the best checkpoint, from step 14,000.

| Metric | CrowGPT2 | Candidate |
|---|---:|---:|
| Best validation loss (lower is better) | 4.6860 | 4.7925 |
| Units/bout | 4.23 | 3.38 |
| Gaps/clip | 3.37 | 2.60 |
| Single-unit share | 0.20 | 0.31 |
| Median gap (seconds) | 0.267 | 0.309 |
| Dust rate | 0.256 | 0.244 |

The candidate fails three of four predefined screening checks. Dust is
roughly unchanged; structure moves away from the real reference (5.10
units/bout, 4.16 gaps/clip). This recipe is not an instrument improvement.
The micro-batch and stochastic-validation caveats above still apply; this
is evidence about this candidate, not a universal ruling against capacity.
24 diagnostic clips were saved, 12 per arm. No listening pool is registered.

## What it changed

Keep CrowGPT2 as the release. Preserve the candidate and its samples for
inspection, but the screen does not justify promoting it or spending a
formal listening sitting on it by default. Increasing width and depth with
this optimizer recipe did not improve the measured output. Results and raw
measurements are in results.json.
