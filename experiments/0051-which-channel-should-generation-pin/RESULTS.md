# Which channel bucket should generation pin?

## Overview

The generator can be conditioned on a "channel" token that names which recording-channel cluster a clip should sound like, and experiment 0044 had tested that token by pinning the first bucket in the vocabulary — then found no benefit. This experiment asked whether that was the right bucket to pin, by measuring stage-0 churn (the offline stickiness signature from experiment 0046) for thirteen different pinned buckets on one existing checkpoint. The answer: the bucket 0044 pinned was the worst of the thirteen. It is the fallback bin that collects every recording the pipeline could not characterise, so 0044 effectively compared "no channel token" against "a token naming the average of everything". A deliberately chosen bucket, `channel-205`, lands within 0.009 of real audio's churn, and bucket choice turned out to move churn across a 0.215 range — a lever as large as any sampling knob. The 0044 null is therefore void as evidence about channel conditioning.

## In depth

**Question.** Experiment 0044 asked whether the channel token helps and answered no (P(channel256 preferred) = 0.600 at n=20, unresolved), pinning `vocabulary.channels[0]`. Was that the right bucket? No: `channel-000` is k-means label 0 — its identity is sklearn's arbitrary label order — and it is also `ChannelBuckets.fallback`, so every recording the describer could not characterise lands there by design. It collects 448 distinct American Crow recordings against a median bucket of 46. `Sampler._prefix` says in its own docstring that which bucket to pin is "a caller's choice worth making deliberately"; nobody had made it.

**Method.** Stage-0 churn (the fraction of adjacent frames whose coarse code changes, from experiment 0046) on 40 clips per pinned bucket from the existing `model-channel256`, against real audio's 0.868. No training, no listener. Thirteen buckets were chosen to span both ends of three criteria, only one of which is BirdNET — selecting candidates on crow confidence alone would be circular, since BirdNET selected the corpus. `human` is one archive's 0–5 stars and the other's A/B/C on a common 0–1 scale, assigned by people before this project existed. `flatness` is the geometric-over-arithmetic mean of each bucket's mean quiet-frame mel spectrum: a hissy channel is spectrally flat, a clean one has rolloff. Absolute quiet-frame level is deliberately not a criterion, because `describe_corpus` does not normalise, so level is recording gain as much as noise floor. Eligible buckets needed at least 150 American Crow bouts and 15 recordings; 139 of 256 qualified.

**Numbers.**

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

The pinned bucket moves stage-0 churn across a 0.215 range — larger than anything experiment 0047's sampling sweep reached without mangling the distribution, and all within one checkpoint, so it is the token and not the training run. Five buckets sit closer to real audio than the unconditioned control, and `channel-000` is not one of them: it overshoots by +0.059 where the control undershoots by −0.049, so 0044's channel arm was worse on this measure than not using the token at all, ranking 12th of 13. `channel-205` lands at −0.009 — about five times closer than the control, comparable to 0047's best sampling knob (repeat 1.05 at −0.0025) and reached by a completely independent lever.

Direction matters and it flips. The incumbent's defect is stickiness (undershoot); pinning a hissy bucket makes it stickier still, while pinning the mixture bucket overshoots into jitter, which 0047 warned "has its own sound and is not obviously better". Only a middle band lands on real audio.

**What predicts churn** — Spearman over the 13 arms with a 20,000-draw permutation p:

| predictor | rho | perm p |
|---|---|---|
| flatness | **−0.659** | **0.017** |
| birdnet | −0.516 | 0.072 |
| recordings | +0.363 | 0.217 |
| human | −0.313 | 0.301 |
| bouts | −0.038 | 0.909 |

Quiet-frame spectral flatness is the only predictor that resolves, and it is not BirdNET and not the human rating: hissier channel, stickier generator. Five predictors were tested, so Bonferroni puts that 0.017 at 0.085 — suggestive, not established. Note what did not predict: bucket size in either bouts or recordings (so this is not "narrow buckets are easier"), and human recording quality — `channel-007`, with human rating 0.958 and the top BirdNET at 0.913, is the second stickiest arm at −0.140.

Fragment counts are a second axis and do not track churn. Experiment 0044 found sub-second clips "instantly loose" and made `MIN_GRADEABLE_SECONDS` refuse them, so a bucket that only reaches target churn by emitting many discards is a bad candidate for a sitting: `channel-155` needed 39 discards and `channel-171` 33, against `channel-205`'s 6.

**Conclusion.** `channel-205` is the bucket that earned a sitting: stage-0 churn −0.009 from real, the lowest discard count of any on-target arm, 22 recordings and 164 bouts behind its embedding, and the least-hiss quiet spectrum in the sweep. The backup is `channel-113` (+0.018, 9 discards, 81 recordings). This does not say the channel token helps — churn is a mechanism, not audibility; experiment 0049 put it at 1 for 2 as a ranker and demoted it to triage. What it establishes is narrower and still worth having: 0044 measured the hypothesis at the wrong setting, its null does not bear on whether pinning a deliberately chosen channel helps, and there is now a principled, offline, non-BirdNET way to choose which bucket to put in front of a listener.

**What this changed:**

- **0044's channel null is void as evidence about channel conditioning**, for a reason independent of its power: the arm pinned the fallback sink, which measures worse than the unconditioned control. The re-test is `channel-205` against `fair-k8`, forced choice, needing no training.
- **`channels[0]` is not a safe default and `Sampler._prefix` should stop offering it** — either require the channel explicitly or default to a bucket recorded in the manifest as chosen.
- **`fallback="channel-000"` collides a real learned bucket with the unknown bin.** It should be renamed `channel-unknown` so it can never be pinned by accident and can never absorb training mass into a bucket that also means something.
- **`data/crowgpt/channels.json` is stale and fails silently.** It was fit on 12,741 recordings; the index now holds 19,797, so 7,056 are unmapped and `assign` routes every one to the fallback — corpus-wide, 46,637 of 127,553 bouts (36.6%) in one bucket. American Crow is barely touched (347 unmapped, 4.4% of its bouts), so this experiment stands, but any channel-conditioned run on the 46-species v2 corpus must refit first.
- **Quiet-frame spectral flatness is a candidate pre-gate** for which channel to pin, at zero cost from `channels.json` alone, with no audio and no BirdNET. It needs one more sweep to survive multiple comparisons.
- **Bucket choice is a lever of the same size as the sampling knobs**, and the two are independent, so `channel-205` and `repeat_penalty=1.05` compose in principle. Neither had been heard when this was written; the honest next step is one sitting testing them against the incumbent rather than two run serially.

Cost: 30 seconds for the ranking and 15 minutes for the sweep, no listener. `ranking.json` holds all 256 buckets; `results.json` and `analysis.json` hold the sweep.
