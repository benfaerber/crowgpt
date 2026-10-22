# 0086 — can tuned training improve CrowGPT2?

2026-09-10. Ben authorized the controlled learning-rate comparison and made
the GPU available. Status: completed successfully 2026-09-10 16:38 MDT. All three 30k runs,
full-validation selection, generated comparison and pool registration finished.

0085 lost on validation and generated structure, but copied the smaller
model's optimizer recipe and chose checkpoints using moving random validation
batches. Its selected step-14k loss was an isolated dip, and early stopping
ended the 30k schedule at 22k. These observations motivate this experiment;
they do not prove that checkpoint noise caused the audible/structural loss.

## Design, before results

Three d512/L12/H4 models, 43,859,968 parameters, peak learning rates
0.0001, 0.0002, 0.0003. Each starts from the same seed-0 initialization and
sees the same sequence of training batches. Same tokens-6s, species mix,
eight codebooks, units/duration prefix, zero dropout, cosine floor 0.1,
200-step warmup and 30,000 optimizer steps. No early stopping. A true batch
of eight (no accumulation) passes the longest-batch test at 9.37 GiB peak.
The six-second window and finetuned decoder remain fixed.

**This tests the optimizer settings on the larger model.** Relative to 0085
it also changes effective loss weighting from two micro-batch means to one
true eight-example token mean, and removes early stopping. Only the learning
rate differs among the three new arms. The historical CrowGPT2 checkpoint is
a product comparator, not a newly trained causal size-control arm.

Every 1,000 steps evaluate the same 256 canonical American Crow training
bouts and the same 256 canonical validation bouts, each panel drawn without
replacement with one bout per recording group. Selection deliberately targets
American Crow; other-species quality is not assessed. Evaluation sums loss over
non-padding target tokens and divides by the total token count. Training RNG
is untouched by evaluation. Panel indices and token-index hashes are saved.
Two actual GPU evaluations of the same preflight model repeated exactly.

Save best-panel and latest weights every evaluation, plus snapshots at
5k/10k/15k/20k/25k/30k. A separate atomic resume.pt contains model, AdamW state,
step, schedule configuration, history, RNG states and batch sampler state.
A restarted chain validates its recipe before continuing and loses at most
999 optimizer steps from an unexpected stop. Finished arms are skipped by
resuming at step 30k. A deliberate interrupted CPU test with dropout matched
uninterrupted weights, history and optimizer tensors exactly.

After all three arms finish, score their saved snapshots and best-panel
checkpoints on **all 5,033 canonical American Crow validation bouts**. Duplicate
steps are scored once. Rescore CrowGPT2 and 0085's checkpoint identically;
historical best_val numbers are not used in this comparison. Select the new
candidate with lowest full-validation token-weighted cross entropy. This is
validation used for model selection, not an unbiased final test score.

## Generated comparison and ears

The selected candidate and CrowGPT2 each produce 100 gradeable fresh draws
(T 1.1, k 200, 460-frame cap, finetuned decoder, seeds starting at 86000).
Report units, gaps, single-unit share, median gap, the existing marginal dust
probe and late-minus-early burst pitch strength (0072's crescendo). Save all
attempted seeds, including outputs rejected solely for insufficient length.
The instrument reference is 200 real six-second test bouts, each from a
separate group. Probe scores are diagnostic orderings, not promises of an
audible difference; 0069/0070's caveats apply.

Separately draw 44 clips per arm from seeds starting at 88000. No quality
ranking or cherry-picking: accept the first gradeable clips. Build listening
pool **capacity-0086**: 40 anchored candidate/CrowGPT2 comparisons plus eight
real/generated catches. Three doses of 16, 30-minute cooldown, results withheld
until all 48 answers; each dose balances candidate side and real-catch side.
No clips repeat within the pool. The 56 real clips use new test groups,
excluding recorded anchors from previous pools. Generation gate and listening
use disjoint seed ranges; real reference and real listening anchors are disjoint.

The pool is built regardless of instrument ranking: this experiment explicitly
asks whether the strongest tuned candidate sounds better. No release is
changed automatically. A pass by ear, not lower cross entropy alone, is required
for a CrowGPT3 release decision.

## Running and artifacts

    crowgpt/.venv/bin/python experiments/0086-can-tuned-training-improve-crowgpt2/run.py

Use --preflight-only for the GPU/memory/repeatability check. Re-running the
same command resumes saved arms. Checkpoints and full evaluation outputs live
under crowgpt/results/tuning-0086; each arm has its own directory, recipe.json,
history.json and resume.pt. select/compare/pool work lives in finish.py and
can be rerun separately. It refuses to overwrite an existing listening pool.

The user service is crowgpt-tuning-0086, with a nine-hour runtime ceiling.
Live dashboard cards: 0086 tuned CrowGPT3 and 0086 results and listening.
Journal: journalctl --user -u crowgpt-tuning-0086. Expect roughly 5–7 hours for
training, checkpoint evaluation and pool generation; measured progress is the
source of the current ETA. A timeout preserves the latest saved training state.

The training implementation is experiment-local in training.py; no existing
model, release or shared Trainer behavior changes. Unit tests cover exact
resume, incompatible-recipe refusal, fixed-panel repeatability, padding/token
weighting and unique, side-balanced listening doses.

## Results

The chain completed in 5 h 51 min. Every learning-rate arm's strongest saved
checkpoint on full American Crow validation was its final step 30,000:

| Model | Full AC validation CE |
|---|---:|
| CrowGPT2 | 4.7927 |
| 0085 candidate | 5.0367 |
| 0086 LR 0.0001 | 4.9453 |
| 0086 LR 0.0002 | 4.9388 |
| **0086 LR 0.0003, selected** | **4.8690** |

The original learning rate wins this comparison. The selected model improves
on 0085, while CrowGPT2 retains the lower loss on the identical evaluation.
These scores replace cross-run comparisons of historical best_val numbers.
The change from 0085 combines a complete schedule, true-batch weighting and
checkpoint selection; it does not isolate which change helped.

Fresh generated comparison, 100 gradeable draws per arm:

| Metric | CrowGPT2 | Selected candidate |
|---|---:|---:|
| Units/clip | 3.94 | 4.06 |
| Gaps/clip | 3.11 | 3.17 |
| Single-unit share | 0.22 | 0.23 |
| Median gap, seconds | 0.277 | 0.288 |
| Dust-probe fraction | 0.349 | 0.236 |
| Late-minus-early pitch strength | +0.0249 | −0.0007 |

Structure holds on these draws and the dust probe is directionally improved;
neither is a demonstrated audible improvement. Dust denominators are 83 and
89 feature-eligible clips respectively; all attempted draws are retained in
the output artifacts. Crescendo does not improve. The real-reference sample
is fresh and differs from earlier experiments, so its absolute counts should
not be compared to prior reference means as though the corpus changed.

Listening pool **capacity-0086**, ID 7, is registered and the page responds:
48 trials, doses of 16, 30-minute cooldown, result reveal at 48. No answers
were inspected for this report. Full selection and gate summaries are in
results.json; raw generated metrics and pool specification are under
crowgpt/results/tuning-0086.

## What it changed

A stronger candidate than 0085 is ready for blinded listening, with the
structure regression resolved in this draw set. Lower learning rates did not
help. CrowGPT2 remains the release while the ear decides the selected
candidate's quality. All arms' best saved checkpoints occurring at the final
step keeps longer training a testable follow-up; it is not evidence that an
extension must improve the sound. GPU reservation released at completion.
