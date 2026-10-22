# 0055 — which generated calls are good enough to publish?

## Overview

Ben wanted the generator's own output on the promo site; experiment 0054 had ranked his field recordings, which answered a different question. This experiment drew 300 clips from `model-mono-v2` (chosen because it was not under test in the still-running blinded experiment 0053), scored every candidate with two instruments — BirdNET confidence to rank and stage-0 churn to veto — and shortlisted 10 clips. The striking result is how rarely the two instruments agree: only 3 of 203 analysable clips cleared both a BirdNET score of at least 0.99 and a churn within 0.02 of real audio. The shortlist waits on Ben's ear; the ranking chooses what gets listened to, it does not decide.

## In depth

### Two constraints, one solved

**Blinding — solved by not using the model under test.** Experiment 0053 was mid-flight (50 of 120 trials graded, results withheld, arms being three channel buckets of `model-channel256`). Curating a best-of from that model and playing it to Ben would leak arm quality into a running experiment. These clips come from `model-mono-v2`, which is not in the pool, and no filename records a bucket. Experiment 0050 put mono-v2 and fair-k8 at a dead heat (P = 0.51), so nothing was given up. The risk is reduced rather than removed — hearing a curated best-of shifts an absolute bar, and experiment 0038 measured 8.3 points of drift from less — but every 0053 trial carries its own real reference, so a moved criterion affects both arms of a comparison equally. Whether to listen now or after trial 120 is Ben's call.

**Licensing — flagged, not solved.** The model trained on archive recordings, some CC BY-NC-ND, and `crowgpt/README.md` already forbids publishing derived shards. Generated audio is not a shard, and experiment 0015 found n-gram overlap with the training set at 0.0× the held-out base rate at T = 1.0, the setting used here — real evidence the model is not reproducing anyone's recording. Whether a model's output is a derivative work of ND material is unsettled, and this experiment is not where that gets decided. Attribution on the page ("trained on public-archive recordings") is cheap and worth it regardless.

### Method

300 draws from `model-mono-v2`, American Crow, at the measured sampling defaults (T = 1.0, top-k 200 — both measured twice, never typed). 203 cleared 1.5 s, which is BirdNET's floor rather than the page's: `birdnetlib` breaks out of its chunking loop below that and returns zero detections with no error, so a shorter clip reads as rejection when nothing was analysed.

Two instruments, neither trusted alone:

- **BirdNET corvid confidence ranks.** It is circular as evidence that the generator is good — experiment 0022 found generated output scores above real audio on it — but for choosing the most crow-like of 203 clips, a classifier's confidence is a fair ranking even when its level is inflated.
- **Stage-0 churn vetoes**, against real audio's 0.868 (experiment 0046). The defect Ben calls "modem" is a stuck coarse codebook, so a clip far off on churn carries the artefact. Anything more than 0.12 away is dropped.

### Numbers

| | |
|---|---|
| draws | 300 |
| over 1.5 s | 203 |
| survive the churn veto | 144 |
| BirdNET ≥ 0.90 | 139 |
| BirdNET ≥ 0.99 | 23 |
| clear both instruments (≥ 0.99 and within 0.02) | **3** |

Median generated churn is 0.812 against real audio's 0.868 — the stickiness experiment 0046 measured, showing up again on a checkpoint 0046 never saw. Durations run 1.51–2.99 s and pile up at the top (87 of 203 in the 3.0 s bin) because 3.0 s is the bout cap the corpus was built on; the model has nothing longer to imitate.

### The shortlist

| # | secs | BirdNET | churn | gap | clears both |
|---|---|---|---|---|---|
| 1 | 3.0 | 0.991 | 0.870 | +0.002 | yes |
| 2 | 3.0 | 0.995 | 0.873 | +0.005 | yes |
| 3 | 2.9 | 0.992 | 0.886 | +0.018 | yes |
| 4 | 2.6 | 0.994 | 0.809 | +0.059 | |
| 5 | 1.9 | 0.985 | 0.764 | +0.104 | |
| 6 | 1.6 | 0.945 | 0.884 | +0.016 | |
| 7 | 2.8 | 0.997 | 0.830 | +0.038 | |
| 8 | 3.0 | 0.997 | 0.830 | +0.038 | |
| 9 | 2.8 | 0.996 | 0.907 | +0.039 | |
| 10 | 2.9 | 0.996 | 0.811 | +0.057 | |

Clip 1 is the one to beat: churn 0.002 from real audio and BirdNET 0.991. Only three of 203 clear both instruments, which is worth noticing on its own — the two instruments are close to independent here, and agreement between them is rare rather than automatic.

### The selection bug worth recording

The first version seated the shortlist by BirdNET confidence and then applied a duration-spread rule, which pushed two of the three dual-instrument clips out of the shortlist entirely — including the best one, at gap +0.002. A diversity rule applied before a quality rule silently discards the thing being looked for. Fixed by seating clips that clear both instruments first and unconditionally, then spreading durations across whatever slots remain.

### What this changed

- A re-derivable "best generated clips" list exists (`candidates.json`), with both scores recorded against each of the 203 candidates rather than a folder curated once by hand.
- A dual-instrument screen exists and is cheap: BirdNET ranks, churn vetoes, agreement is rare (3 of 203). It is a usable filter for any future "pick a demo clip" job, costing one GPU pass plus a BirdNET batch.
- Median churn 0.812 against 0.868 reproduces experiment 0046's stickiness on a checkpoint it never saw — a small independent confirmation nobody asked for.

**Not decided here:** which clips go on the page, and whether generated audio should go on a public page at all given the ND question. Both are Ben's.
