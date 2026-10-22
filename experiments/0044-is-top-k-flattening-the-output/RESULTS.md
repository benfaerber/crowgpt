# Is top-k flattening the output?

## Overview

Experiment 0043's offline timbre instrument said the project's long-standing `top_k=200` sampling default was flattening generated audio, and that turning it off put the timbre statistics on top of real audio. This experiment put the question to the ear: two blinded forced-choice sittings of 60 trials each, comparing the shipped setting against no top-k, with a channel-conditioned model as a second pairing. The ear said the opposite of the offline instrument: `top_k=200` was preferred, resolved (p = 0.027), and it replicated across both sittings, so the default stays and the offline instrument is retired as a ranker. The sitting also uncovered a systematic flaw in every earlier listening test — real clips had been filtered for minimum length while generated clips were not, so a share of the "modem" defect attributed to the model for thirty experiments was actually sub-second clips in the grading pool.

## In depth

### Why

`top_k=200` had never been judged by ear at the shipped temperature. It is not a uniform truncation — measured per stage on `model-fair-k8`, top-200 of 1024 retains 0.981 of the probability mass at codebook 0, 0.889 at codebook 3, 0.805 at codebook 6 and 0.782 at codebook 7 — nearly a no-op on coarse structure, discarding about a fifth of the fine residual. Structurally that is the same as cooling the fine stages, which `stages.py` pre-registered as what "robotic" would sound like. It was never caught because 0019 checked top-k only against EOS, and 0015's sweep found turning it off hurt at every temperature except 1.00 — the shipped setting — with evidence from BirdNET detection, which 0014 established cannot hear quality. 0043's offline instrument then said `top_k=None` put frame-to-frame timbre at 0.0422 against real's 0.0413 and within-clip at 0.0620 against 0.0572, neither resolved from real, while the shipped setting sat resolved below both — but that instrument had reversed sign between checkpoints, so it did not get to decide alone.

A second question rode along: `model-channel256`, the incumbent's exact recipe plus one prefix token naming which of 256 background-spectrum buckets the recording came from — the honest test of 0042's channel-averaging mechanism. Sampling pins one bucket, since drawing it per clip would restore exactly the averaging the token exists to remove. Both sides of that pairing run at `top_k=200`.

### Method

`PairPage` forced choice (from experiment 0041), one question — which of two clips is less robotic. Per sitting: 30 pairs top_k=200 vs top_k=None, 20 pairs fairk8 vs channel256, 10 catch trials real vs generated, scored separately. Protections, each already paid for elsewhere: model-against-model pairings only, with real confined to catch trials; sides balanced within each pairing rather than randomised (0041 measured a 65% left bias); distinct seed blocks per arm; real bouts consumed, never reused (`ALREADY_USED = 370` across 0033–0041); every clip peak-normalised; and — after the first build shipped 0.1-second clips — every clip at least 1.0 s, generated arms included, with arms over-drawn to hold their stated n.

The discard rate at the 1.0 s minimum is itself a result:

| arm | kept / drawn | discarded |
|---|---|---|
| topk200 | 40 / 49 | 18% |
| notopk | 30 / 37 | 19% |
| fairk8 | 20 / 25 | 20% |
| channel256 | 20 / 33 | 39% |

`model-channel256` stops early twice as often as the incumbent, and its median surviving clip is 1.92 s against 2.37–2.53 s for every other generated arm — an unpredicted length defect the channel token appears to have made worse. Top-k makes almost no difference to it (18% vs 19%), so early stopping is not what top-k does.

### Results

Two sittings, both 60/60 rated. The second is a replication on fresh draws — the page was rebuilt with new seeds after the 1.0 s filter went in, so pooling does not double-count.

| | morning (unfiltered) | evening (filtered) | pooled |
|---|---|---|---|
| P(notopk preferred) | 0.400 [0.246, 0.577] | 0.300 [0.167, 0.479] | 0.350 [0.242, 0.476] |
| P(channel256 preferred) | 0.550 [0.342, 0.742] | 0.650 [0.433, 0.819] | 0.600 [0.446, 0.737] |
| catch, P(real) | 10/10 | 10/10 | 20/20 |
| side, P(left) | 0.600 | 0.450 | 0.525 |

`top_k=200` is preferred, 39 of 60, p = 0.027, and it replicates — both sittings point the same way and the filtered one points harder. This is the opposite of 0043's offline prediction. The controls hold: catch accuracy is 20/20, side bias is 0.525 pooled, and in the evening sitting the longer clip won only 0.444 and 0.517 of decided trials by pairing, neither resolved, so length is not answering the question. `model-channel256` does not resolve: 24 of 40 pooled, CI [0.446, 0.737], directionally favourable in both sittings and never separated.

Per the mapping written before the sitting, 0043's measurement stops being used to rank arms: frame-to-frame and within-clip timbre movement measure something real that does not correspond to what a listener calls robotic. With 0042's sign reversal that is two independent failures of the same instrument. The offline pre-gate cost about four minutes of GPU and was wrong, which is exactly what a pre-gate is there to find out cheaply.

### The bigger finding: every earlier sitting was unfair to the generated arm

Ben after the first sitting: "too short clips instantly loose. 0.1 second is always worse. The vibe of the crow is there with some of them. It is starting to grasp crow." After the second: "that def removed many of the modem sounds! it still sounds 'scratchy' not modem like. Before it had background beeps now it sounds like a hoarse crow." The only difference between the sittings is the 1.0 s filter, so a share of what the project called "modem" and "background beeps" for thirty experiments was sub-second clips in the grading pool, not the model.

It is systematic and one-sided: in 0028, 0033, 0034, 0037, 0038 and 0041 the minimum-length filter was applied to the real bout store and nothing else. Measured here, 18–20% of generated clips fall under one second (shortest 0.08 s). Every real-versus-generated number in the series is depressed on the generated side by up to that share — very large in relative terms against a generated good-rate of 0.21–0.25 — though generated-vs-generated comparisons carried the same handicap on both sides and are unaffected. What remains after the filter is "scratchy" and "hoarse", the exact word Ben used for the codec round-trip with no model involved (0024 Part 3), so the model's share of the remaining defect may be smaller than thirty experiments assumed.

### What this changed

- `top_k=200` stays; the recommendation to change it is retracted. A one-line change with a clean offline story lost by ear, twice.
- 0043's instrument is retired as a ranker, on its own pre-registered terms.
- The channel token stays in the code and off by default: unresolved at n=40, and it discards 39% of draws for being under a second against the incumbent's 18%.
- Every listening page must filter generated arms by length, not just real ones — a durable fix belonging in one place rather than in each experiment's `run.py`, where it was got wrong six times.
- The series' real-vs-generated gaps (0028, 0033, 0034, 0037, 0038, 0041) are re-read as upper bounds, since all graded filtered real audio against unfiltered generated audio.
