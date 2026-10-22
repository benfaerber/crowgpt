# 0045 — Does the delay pattern help?

**2026-08-04/05** · 60 forced-choice pairs + 10 catch · **answer: no, and it was
the last untried modelling idea**

## The question

Every other route was closed. Four tokenizer configurations moved nothing (0028,
0032–0037). Capacity was ruled out twice, at two sequence lengths (0023, 0038).
Shortening the sequence hurt badly (0038). The extender died on DAC's near-white
fine stages (0035). What had never been varied was the **objective**: every model
in this project predicts the next token over a *flat interleaved* stream.

Flat was the suspect for a specific reason. At position (t, k) the model predicts
codebook k of frame t from codebooks 0..k−1 of the **same frame** plus everything
before, so fine stages hang off a coarse prediction made three tokens earlier and
errors compound inside a frame — a plausible shape for 0027's "right structure,
wrong texture". MusicGen reports flat interleaving as the worst of its four
layouts and the delay pattern as the fix.

Matched to `model-fair-k8` exactly — d384/L8/H6, effective batch 18, dropout 0,
30,000 steps, same corpus, same codec. **Only the token layout moved.**

## Result

| | |
|---|---|
| P(delay preferred) | **0.53**, CI [0.39, 0.67] |
| side-balanced | 0.53 |
| too close to call | 11 of 60 |

**Not resolved, and the point estimate is a coin flip.** At 60 pairs this
resolves roughly a 13-point difference, so the delay pattern is worth less than
that. The catch set came in at 8/10 for real, wider than previous sittings but in
the right direction.

**The last modelling idea is a null.** Combined with everything above, no change
to the tokenizer, the capacity, the sequence length, the architecture or the
token layout has moved generated audio. That is now five independent routes and
one conclusion.

### The offline screen predicted it

0046's churn metric, measured *before* the sitting, put the delay model at
stage-0 churn 0.780 against `fair-k8`'s 0.801 and real's 0.868 — i.e. **stickier,
not less.** The ear then found no difference at all.

So the screen called the direction right (not an improvement) while overstating
the size (it suggested worse, the ear said same). That is the first time an
offline instrument in this project has anticipated a listening result rather than
contradicted it, and it cost two minutes against the sitting's hour. Worth
keeping, worth not over-trusting.

## Ben's fix answered its own question immediately

He proposed playing a random side first, to separate a left-**button** bias from
a first-**heard** bias. Until 0045 the left clip was always played first, so the
two were the same measurement wearing two names. Balanced as a 2×2, they
separate cleanly:

| | rate | 95% CI | |
|---|---|---|---|
| left chosen | **0.66** | [0.54, 0.78] | **resolved** |
| first-heard chosen | 0.49 | [0.37, 0.63] | not resolved |

**The bias is the button, not the order.** Left replicates almost exactly across
sittings (0.65 in 0041, 0.66 here), and hearing a clip first is worth nothing at
all — 0.49 is as close to no effect as 59 trials can show.

That settles a question that had been an assumption, and it means the balancing
that matters is of *sides*; randomising play order is harmless and was the only
way to learn this, but it is not doing bias-control work.

## What this changed

- **The modelling route is exhausted.** Five ideas, five nulls. Anything further
  on the generator needs a genuinely new class of idea, not another variant of
  one already tried.
- **One cheap thing remains before pivoting.** 0047 found a repetition penalty of
  1.05 lands on real audio's stage-0 churn (0.866 against the 0.868 target) where
  the current default sits 0.049 short. It is a sampling change, needs no
  training, and has never been heard. That is one sitting, not one night.
- **The honest next move after that is the context work.** 0040 showed Phase 3's
  "call types do not cluster" was measured in a space where the microphone
  outranks the species, so the question the project actually exists to answer has
  never been properly asked. That is where the remaining value is.
- **The offline screen earned a place.** It predicted this null before the
  sitting. Use it to triage, never to decide.
- **Left-button bias is confirmed and order bias is refuted**, so future pages
  need side balancing and nothing else.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0045-does-the-delay-pattern-help/run.py
```

Tokenize 14 min, train 63 min, generate 4 min. Session in
`crowgpt/results/listening/delay-0045/`.
