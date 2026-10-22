# 0071 — does duty cycle predict the scream?

**2026-08-11, predictions before results** · 30 fresh draws, tags blind,
one statistic on trial · **answer: pending Ben's tags**

## The question

0059 separated Ben's one tagged scream (model-fair-k8 seed 4) from five
same-page draws on duty cycle alone — 0.142 against 0.292–0.603, no
overlap — and called it what it was: a nomination from n = 6 with one
positive, picked after looking at the table. The test it prescribed is
this experiment: ~30 fresh draws, Ben tags scream / no-scream blind, and
duty cycle predicts the tags or dies.

Stakes from the TODO entry: if it holds, the 0055 shortlist gets a scream
filter for free (it already computes churn at pick time and duty sits
beside it). If it dies, the scream has no signature in the coarse
statistics, which points at the fine stages or the decode. Worth carrying:
churn0 is blind to the scream (0.859 vs real 0.868), so 0053's instrument
waves screams straight through.

## Design

30 draws from model-fair-k8 at seeds 100+ (fresh — 0057/0059 used 2–7),
**frozen decoder**, matching the conditions the exemplar was tagged under.
The page is a RatingPage wearing scream labels (`build_page.py` →
`crowgpt/results/scream-tag-0071.html`): tag each clip Scream / No scream
/ Unsure, waveform hidden until tagged, **duty cycle deliberately kept out
of the post-rating reveal** — the reveal shows only the seed, because a
number Ben can see mid-page trains his ear on the statistic and makes the
last twenty tags circular. Duty, churn, and the rest live in
`manifest.json` here and join on `clip_id` at analysis.

Grade it in one visit, then feed the downloaded `rating-*.json` to
`analyse.py`.

## Predictions (written before running)

- Base rate: 3–8 screams in 30 draws (0057's page had 1 in 6).
- **Duty cycle predicts the tag at AUC ≥ 0.8**, direction low-duty =
  scream, with the tagged screams concentrated under ~0.2 — the exemplar's
  0.142 was not luck.
- churn0 stays blind (AUC ≤ 0.65), reconfirming that the scream needs its
  own gate rather than sharing 0053's.
- Named failure: duty AUC lands under 0.7 — then the signature nomination
  dies, the scream joins blowing-dust in the "described but unmeasured"
  column, and the next probe is fine-stage or decoder-side, not envelope
  statistics.

## Result — pending
