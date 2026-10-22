# 0051 — which channel bucket should generation pin?

**Question.** 0044 asked whether the channel token helps and answered no
(P(channel256 preferred) = 0.600 at n=20, unresolved). It pinned
`vocabulary.channels[0]`. Was that the right bucket to pin?

**No, and it is the worst of the thirteen tested.** `channel-000` is k-means
label 0 — its identity is sklearn's arbitrary label order — and it is also
`ChannelBuckets.fallback`, so every recording the describer could not
characterise lands there by design. It collects 448 distinct American Crow
recordings against a median bucket of 46. It is the corpus's mixture bucket, and
0044 therefore compared "no channel token" against "a token naming the average of
everything": approximately the averaging the token exists to prevent.
`Sampler._prefix` says in its own docstring that which bucket to pin is "a
caller's choice worth making deliberately". Nobody had made it.

**Method.** Stage-0 churn (0046's measure: the fraction of adjacent frames whose
coarse code changes) on 40 clips per pinned bucket from the existing
`model-channel256`, against real audio's 0.868. No training, no listener. Thirteen
buckets chosen to span both ends of three criteria, only one of which is BirdNET
— candidate selection on crow confidence alone would be circular, since BirdNET
selected the corpus. `human` is one archive's 0–5 stars and the other's A/B/C on a
common 0–1 scale, assigned by people before this project existed. `flatness` is
the geometric-over-arithmetic mean of each bucket's mean **quiet-frame** mel
spectrum, recovered by un-whitening its centroid: a hissy channel is spectrally
flat, a clean one has rolloff. Absolute quiet-frame level is deliberately not a
criterion — `describe_corpus` does not normalise, so level is recording gain as
much as noise floor. Eligible buckets needed ≥150 American Crow bouts and ≥15
recordings; 139 of 256 qualified.

## Numbers

| bucket | stage-0 | gap vs real | recs | human | flatness | fragments |
|---|---|---|---|---|---|---|
| **channel-205** | **0.859** | **−0.009** | 22 | 0.773 | 0.0097 | **6** |
| channel-171 | 0.880 | +0.012 | 61 | 0.548 | 0.2520 | 33 |
| channel-113 | 0.886 | +0.018 | 81 | 0.733 | 0.0163 | 9 |
| channel-192 | 0.849 | −0.019 | 90 | 0.573 | 0.3511 | 11 |
| channel-018 | 0.840 | −0.028 | 37 | 0.588 | 0.3621 | 25 |
| *(control) fair-k8, no channel token* | *0.819* | *−0.049* | — | — | — | *9* |
| **channel-000 · what 0044 pinned** | **0.927** | **+0.059** | 448 | 0.855 | 0.1251 | 12 |
| channel-155 | 0.937 | +0.069 | 23 | 0.605 | 0.0147 | 39 |
| channel-002 | 0.782 | −0.086 | 31 | 0.717 | 0.5109 | 12 |
| channel-186 | 0.750 | −0.118 | 17 | 0.878 | 0.2963 | 6 |
| channel-219 | 0.742 | −0.126 | 24 | 0.875 | 0.2002 | 7 |
| channel-148 | 0.729 | −0.139 | 34 | 0.728 | 0.5509 | 7 |
| channel-007 | 0.728 | −0.140 | 21 | 0.958 | 0.1405 | 4 |
| channel-081 | 0.722 | −0.146 | 52 | 0.715 | 0.5601 | 13 |

**The pinned bucket moves stage-0 churn across a 0.215 range** — larger than
anything 0047's sampling sweep reached without mangling the distribution, and all
of it within one checkpoint, so it is the token and not the training run.

**Five buckets sit closer to real audio than the unconditioned control, and
`channel-000` is not one of them.** It overshoots by +0.059 where the control
undershoots by −0.049, so 0044's channel arm was worse on this measure than not
using the token at all, and it is 12th of 13. `channel-205` lands at −0.009,
about five times closer than the control, comparable to 0047's best sampling knob
(repeat 1.05 at −0.0025) and reached by a completely independent lever.

**Direction matters and it flips.** The incumbent's defect is stickiness
(undershoot). Pinning a hissy bucket makes it stickier still; pinning the mixture
bucket overshoots into jitter, which 0047 warned "has its own sound and is not
obviously better". Only a middle band lands on real audio.

**What predicts churn, Spearman over the 13 arms with a 20,000-draw permutation p:**

| predictor | rho | perm p |
|---|---|---|
| flatness | **−0.659** | **0.017** |
| birdnet | −0.516 | 0.072 |
| recordings | +0.363 | 0.217 |
| human | −0.313 | 0.301 |
| bouts | −0.038 | 0.909 |

Quiet-frame spectral flatness is the only predictor that resolves, and it is
**not** BirdNET and not the human rating: hissier channel, stickier generator.
Five predictors were tested, so Bonferroni puts that 0.017 at 0.085 — suggestive,
not established. Note what did *not* predict: bucket size in either bouts or
recordings, so this is not "narrow buckets are easier", and human recording
quality, so the best-rated channel is not the one to pin (`channel-007`, human
0.958 and the top BirdNET at 0.913, is the second *stickiest* arm at −0.140).

**Fragment counts are the second axis and they do not track churn.** 0044 found
sub-second clips "instantly loose" and made `MIN_GRADEABLE_SECONDS` refuse them,
so a bucket that only reaches target churn by emitting many discards is a bad
candidate for a sitting. `channel-155` needed 39 discards and `channel-171` 33,
against `channel-205`'s 6.

## Conclusion

**`channel-205` is the bucket that earned a sitting**: stage-0 churn −0.009 from
real, the lowest discard count of any on-target arm, 22 recordings and 164 bouts
behind its embedding, and the least-hiss quiet spectrum in the sweep. The backup
is `channel-113` (+0.018, 9 discards, 81 recordings).

**This does not say the channel token helps.** Churn is a mechanism, not
audibility; 0049 put it at 1 for 2 as a ranker and demoted it to triage, and the
rule from that stands — churn can say a model is broken, it cannot say which of
two working ones sounds better. What this establishes is narrower and still
worth having: **0044 measured the hypothesis at the wrong setting**, its null
does not bear on whether pinning a *deliberately chosen* channel helps, and there
is now a principled, offline, non-BirdNET way to choose which bucket to put in
front of a listener.

## What this changed

- **0044's channel null is void as evidence about channel conditioning**, for a
  reason independent of its power: the arm pinned the fallback sink, which this
  measures as worse than the unconditioned control. The re-test is
  `channel-205` against `fair-k8`, forced choice, and it needs no training.
- **`channels[0]` is not a safe default and `Sampler._prefix` should stop
  offering it.** The docstring already says the choice is the caller's; the code
  then makes it silently, and the value it picks is the fallback bucket.
  Either require the channel explicitly or default to a bucket recorded in the
  manifest as chosen.
- **`fallback="channel-000"` collides a real learned bucket with the unknown
  bin.** Rename it `channel-unknown` so it can never be pinned by accident and
  can never absorb training mass into a bucket that also means something.
- **`data/crowgpt/channels.json` is stale and fails silently.** It was fit on
  12,741 recordings; the index now holds 19,797, so 7,056 are unmapped and
  `assign` routes every one to the fallback. Corpus-wide that is 46,637 of
  127,553 bouts (36.6%) in one bucket. American Crow is barely touched (347
  unmapped, 4.4% of its bouts), so this experiment stands, but any
  channel-conditioned run on the 46-species v2 corpus would train
  `channel-000` as the average of everything and then pin it by default. Refit
  before that run.
- **Quiet-frame spectral flatness is a candidate pre-gate** for which channel to
  pin, at zero cost from `channels.json` alone with no audio and no BirdNET. It
  needs one more sweep to survive multiple comparisons.
- **Bucket choice is a lever of the same size as the sampling knobs**, and the
  two are independent, so `channel-205` and `repeat_penalty=1.05` compose in
  principle. Neither has been heard yet, and the honest next step is one sitting
  that tests them against the incumbent rather than two sittings run serially.

Cost: 30 s for the ranking, 15 min for the sweep, no listener. `ranking.json`
holds all 256 buckets; `results.json` and `analysis.json` hold the sweep.
