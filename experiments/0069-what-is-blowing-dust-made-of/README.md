# 0069 — what is blowing dust made of?

**2026-08-11, predictions before results** · acoustic probe on ear-labelled
clips, then a decoder A/B and a sampling grid · **answer: dust is low
periodicity under a normal envelope, and it is the sound of playing it
safe — conservative sampling makes MORE of it, not less**

## The question

The second 0067 sitting un-convicted the window (pooled 0.507, dead even)
and localised the one defect that matters: **blowing dust** — Ben's bellows
wheeze, *"like when you blow out an old thing and dust comes out"* — and it
wheezes in BOTH arms at the same rate (6 longctx clips vs 7 twin). A
pipeline defect, not a window defect. The sitting also, for the first time,
left behind labelled data: 44 trials with per-clip descriptions, ~88
generated clips wearing his words.

Three questions in a chain, each gating the next:

1. **What does dust measure as?** Ben's description — breath and dust where
   the voice should be, under a correct crow shape — predicts a specific
   signature: low periodicity with normal envelope. Build per-burst features
   on his labelled clips (dust-described vs clean-described, arms pooled
   since the defect is arm-independent) and find which feature separates.
2. **Does the finetuned decoder cause it?** The clips' seeds are in the
   pool spec, so the exact token grids regenerate deterministically; decode
   each through the frozen and the 0063-finetuned decoder and probe-score
   both. The finetune is ear-confirmed on round-trips (0063), but generated
   tokens are off that distribution.
3. **Is it sampling-controllable?** Temperature × top-k grid on the longctx
   model, probe-scored: does any cell cut the dust rate without giving back
   0067's structure gains?

## Design

- **Probe:** clips from pool `longctx-0067b`, labels parsed from the notes
  by `analyse_sitting2.py`'s keyword families (ambiguous lq-real/hq-fake
  halves dropped). Features per burst (0024's segmenter finds the bursts),
  aggregated per clip: pitch strength (normalised autocorrelation peak,
  60–1200 Hz lags), spectral flatness (100–8000 Hz), spectral centroid,
  attack time (10→90% envelope rise). Rank-AUC per feature, dust vs clean;
  the 56 real clips in the pool give the reference distribution.
- **Decoder A/B:** regenerate the described clips' token grids from their
  recorded seeds, decode through both decoder states, compare probe scores
  paired per clip.
- **Grid:** temperature {0.85, 0.95, 1.0, 1.1} × top-k {50, 100, 200, 400},
  40 draws a cell from model-longctx (finetuned decoder, max_frames 460,
  ≥1 s), per cell: dust rate (probe past the Youden threshold), mean units
  per bout, gaps per clip, keep rate. Real 6 s reference from 0067: 5.10
  units, 4.16 gaps.

## Predictions (written before running)

- **Dust is low periodicity under a normal envelope:** pitch strength
  separates dust from clean at AUC ≥ 0.75; spectral flatness follows at a
  lower AUC (dust is noisier); attack time and centroid do NOT separate
  (the envelope is right — that's why the clips fooled nobody but almost).
  Real clips sit above generated-clean on pitch strength — this generator's
  clean is still slightly dusty by nature.
- **The decoder does not cause it:** probe scores track between frozen and
  finetuned decodes (the dust is in the tokens the model writes, not the
  vocoder) — mean paired difference near zero. The alternative (finetune
  worsens dust on generated-token input) would be the single most
  actionable outcome, so it must be genuinely tested, not assumed away.
- **Sampling moves it:** dust rate falls with lower temperature and lower
  top-k — I'd guess the 0.85/50 corner halves the default cell's rate —
  but structure pays: units per bout and gaps per clip drop toward the 3 s
  twin's numbers in the same corner. The interesting outcome is any cell
  with dust clearly below default AND structure within noise of it; I
  predict at least one exists (temperature ~0.95 at moderate top-k),
  because 0044/0047 found sampling knobs buy texture cleanliness before
  they take structure.

## Decision rule

If the probe validates (AUC ≥ 0.7 for any feature), its score becomes the
no-ears dust instrument, the grid's best cell becomes the candidate default
for the next sitting, and the 9–12 s window question (reopened by the
second sitting's tie) waits only on that sitting. If no feature separates,
dust stays ear-only, and the next probe is embedding-side (per-segment
distances of dust clips to their own clean siblings), not acoustic.

## Result

### The probe — right shape, marginal strength

On 11 dust-labelled vs 19 clean-labelled clips (6 real described):

| feature | dust | clean | real | separates? |
|---|---|---|---|---|
| **pitch strength** | **0.388** | 0.508 | 0.518 | AUC 0.699 (dust low) |
| flatness | 0.065 | 0.049 | 0.051 | weakly, 0.593 |
| centroid | 1749 Hz | 1755 Hz | 1530 Hz | no |
| attack | 71 ms | 81 ms | 76 ms | no |

Exactly the predicted signature: dust clips lack periodicity while their
envelope features are normal — breath where the voice should be — and
generated-clean sits indistinguishable from real on this axis, so the
model's problem is not a uniform slight dustiness but a dusty *mode*. The
AUC misses both the predicted 0.75 and the pre-registered 0.7 validation
bar by a hair (0.699 on n = 30), so every downstream number below carries
a **marginal-probe caveat**. The threshold: pitch strength ≤ 0.41 reads
as dusty (Youden 0.50).

### The decoder A/B — not acquitted

Same token grids (regenerated from recorded seeds, n = 29), two decoders:
the finetuned decoder scores **−0.043 pitch strength against the frozen
one** — a third of the entire dust-vs-clean gap, in the dust-ward
direction — and flips the dusty count from 12 to 15. Prediction two
("the decoder is innocent") is **not confirmed**. Not convicted either:
n = 29 through a marginal probe, no significance to claim. But 0063
confirmed the finetune on *round-trip* audio, and generated tokens are off
that distribution — this smells like the finetune adding breathiness
exactly where its training never took it. A focused A/B (round-trips vs
generated tokens, both decoders, the probe plus ears on the worst pairs)
is now a named follow-up.

### The grid — prediction three inverted, and no tradeoff

Dust rate by temperature row (n = 160 per row): **0.49 at T 0.85 → 0.42 →
0.38 → 0.35 at T 1.1.** Falling with MORE freedom, not less — my
prediction ran exactly backwards, and the row-level trend is outside
noise (z ≈ 2.6). Higher top-k also trends cleaner (0.43 at k50 → 0.35 at
k400). Meanwhile structure *improves* in the same direction: mean units
climb from ~4.2 at T 0.85 to ~5.0–5.2 at T 1.1 against real's 5.10.
There is no polish-vs-structure tradeoff to navigate; the predicted
tension does not exist. Best cell **T 1.1 / k 200: dust 0.275, units
4.95, gaps 3.95** against the default T 1.0 / k 200's 0.375 / 4.75 /
3.75. (Absolute dust rates are threshold artifacts — the probe marks far
more clips dusty than Ben's ear does; only the relative ordering means
anything.)

The mechanistic reading, and it rhymes with 0015's "copying or playing it
safe": conservative sampling collapses toward the model's high-probability
tokens, and the high-probability token stream is the *average* caw —
breath-shaped, unvoiced, a bellows. Commitment to a specific voiced caw
lives in the distribution's tails. Dust is not the model reaching and
half-landing (0068 buried that); it is the model NOT reaching. Ben's
instinct that "long context holds more call diversity... it is the
future" and his bellows complaint were never in tension — the same lever
(more freedom) serves both.

## What it changed

- **T 1.1 / k 200 is the candidate sampling default** for model-longctx,
  pending the one thing that can confirm it: a sitting against the current
  default. Queued in TODO.txt as the next ear session.
- **The decoder finetune goes back under investigation** — on generated
  tokens only; its 0063 round-trip verdict stands. Follow-up named above.
- **The probe earns keep-but-sharpen status**: 0.699 on thirty clips, built
  in an afternoon from sitting notes. Every future sitting with per-clip
  descriptions grows its training set for free — the second sitting's
  format is now the format.
- The 9–12 s window rung stays where the second sitting put it: reopened
  in principle, waiting on the dust-controlled sitting before any new
  training spend.

## The dust sitting — the ear cannot tell the cells apart

48 anchored trials (2026-08-12), hot (T 1.1/k 200) vs default
(T 1.0/k 200), same model, same max_frames. `analyse_sitting.py`; the
final 8 ran back-to-back at Ben's request, and the 20+20+8 block plan
that keeps causing that is retired (no-tail-doses rule).

**P(hot) = 0.423 [0.26, 0.61], margin −0.05 — and 14 of 40 compares were
"they are the same",** triple any previous sitting's tie rate. The grid's
promised dust reduction (0.275 vs 0.375 by probe) is not audible at this
n: the sampling cells are ear-equivalent. Length check clean (0.500
exactly). **Catches 8/8 — the first perfect score in the project's
history** — so the ear was sharp; there was simply no difference to hear.

The word cargo agrees: dust-family words land 4-vs-3 and hoarse2 5-vs-8
across the arms — no clean separation. And the defect itself moved up a
rung mid-sitting: Ben named **"hoarse2"**, *"a better sounding version of
blowing dust... many crows screaming... better than hoarse1 but still
audibly hoarse"* — the fifth generation of the signature defect (robot →
scratchy → hoarse → blowing dust → hoarse2), each one a more crow-like
way of being wrong. His overall impression of the pool: "a lot better."

**What it changed:**

- **T 1.1/k 200 becomes the default anyway — adopted on instrument
  grounds, at zero audible cost.** The ear is indifferent; the
  instruments (dust rate, units per bout, gaps per clip, pitch-strength
  parity with real per 0072) all prefer hot; an indifferent ear plus
  unanimous instruments is the one configuration where instruments get
  to decide. The reverse — instruments overruling an ear that
  *objected* — stays forbidden.
- **The probe's marginal validity bit, as flagged:** a 0.10 dust-rate
  difference it reported was not hearable. Its scores stay useful as
  orderings, never as promised audibility.
- **The sampling lever is measured to its audible limit.** Window paused
  at 6 s (0067), sampling now exhausted — the remaining named lever from
  0067's ladder is **capacity**, untested since 0023 and next in line.
- **hoarse2 needs its one fact before any probe:** whether the hoarseness
  lives in one voice or in the pile-up of several ("many crows" co-occurs
  with it in the notes) — a voicing defect and a chorus artifact take
  different probes. One question for Ben, then the probe refits on this
  sitting's ~90 fresh described clips.
