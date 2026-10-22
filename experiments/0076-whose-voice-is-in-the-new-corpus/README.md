# 0076 — whose voice is in the new corpus?

**2026-08-16, predictions before results** · build: ~15 m GPU draws + ~20 m CPU
detection · **answer: pending**

## The question

Ben's ear on the b32 candidate, per button: alarm "screaming like a human",
begging "croaking of a frog", call "hoarse and metallic", song "like an
alien". Four descriptions of wrong *voice* over right *shape* — and every one
of them names a sound that lives in field recordings near crows. The suspect:
model-calltype trained on the pre-scrape corpus (2026-07-31); the 6 s corpus
was extracted 2026-08-11, after the v3 scrape brought in the least-curated
sources. If human speech, frogs and ambience rode in with them, call-type
conditioning would concentrate the contamination per class.

BirdNET's full taxonomy hears more than corvids — human vocal, dogs, engines,
and a great many frogs. So the ear's claim is instrumentable: do the
candidate's draws trigger non-corvid detections that model-calltype's do not,
and does the 6 s corpus itself carry them where the v1 corpus does not?

## Predictions

- The candidate's draws detect as human/amphibian/other-species at a visibly
  higher rate than model-calltype's, per type, matching Ben's descriptions.
- Real bouts from bouts-6s carry more non-corvid detections than bouts-v1 —
  the contamination is in the corpus, not invented by the model.
- The null: both arms detect clean, and the wrong voice is something BirdNET
  cannot hear either (decoder character, EnCodec artefacts) — which would
  point at the codec, not the corpus, and be worth exactly as much.

## Build

`gen_draws.py` (GPU): 20 draws per call type from model-longctx-ct-b32 (460
frames) and model-calltype (225 frames), both through the finetuned decoder,
seeds 42000+; plus 40 real bouts sampled from each of bouts-v1 and bouts-6s,
written as wavs. `detect.py` (CPU, birdnetlib, no torch): full-taxonomy
BirdNET over every wav; tally detections by class per group; report the
non-corvid share and the named offenders.

## Gate (decided before results)

No adoption rides on this — it is a diagnosis. If the candidate's non-corvid
share exceeds model-calltype's by more than noise and the corpus shares
differ the same way, the fix is corpus hygiene (source or confidence
filtering at extract/tokenize) and a retrain, written up as the next
experiment. If both are clean, the codec becomes the suspect and the fix is
not a retrain at all.

## Result — the informative null: nobody foreign is in the corpus

No human vocal, no frogs, no meaningful non-corvid detections in either
arm's draws or either corpus era (5–8% stray single other-bird hits,
symmetric across groups). Ben's "human scream / frog croak / metallic /
alien" is not contamination the model copied — it is the model's own voice
falling short of crow, in a way BirdNET cannot hear.

The corvid-detection tally looked like a second signal (calltype 90% of
draws, ct-b32 69%) until the real-bout rows landed: real 6 s bouts detect at
58%, real v1 at 70%. A generated arm scoring **above real** is the standing
BirdNET-circularity caveat, not realism — so the rate cannot arbitrate
crow-ness and is reported without a verdict.

What the record now excludes, in total: contamination (this), the scrape
corpus at 3 s (0064's ear-tested null), the 6 s window unconditioned
(0067's ear tie). What remains distinguishing model-calltype from the
candidate: the conditioning-on-6s interaction, the units token, and the
optimisation gap — model-calltype trained ~38k steps with n_head 6 at a
true batch 32, while the candidate got 30k steps with n_head 4.

## What it changed

The next cheap move is closing the optimisation gap (0077, if taken):
the candidate recipe at n_head 6 / 40k steps / true batch 32 — every prior
optimisation fix on this corpus has paid (batch alone bought 0.092 val).
If the product of that still loses to model-calltype in Ben's ear, the
deficit is the conditioning×window interaction itself, and the arbiter is
a pool sitting, not another instrument.
