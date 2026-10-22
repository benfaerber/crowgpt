# 0031 — Would a denoiser help?

## Overview

The project had twice cited "would a denoiser help" as a question once measured properly and then lost, so this experiment finally wrote it down. It tested biodenoising (Earth Species Project, arXiv 2410.03427), a Demucs-based denoiser trained on animal vocalisations, against four mower-contaminated field captures. The answer is no — it erases the crow. On three of four captures the denoiser takes BirdNET from a confident American Crow detection to nothing at all, while a free 300 Hz high-pass filter beats every other arm. The denoiser was not adopted.

## In depth

### Method

Captures 94–97: four recordings made in front of the apartment with mowers running (the same set experiment 0008 used), 76 s total. Five arms, each written as a 48 kHz WAV so the analyzer sees identical containers:

| arm | what it is |
|---|---|
| `raw` | as recorded |
| `hp300` | 4th-order Butterworth high-pass at 300 Hz |
| `band16` | 48k → 16k → 48k resample, no denoising |
| `denoise` | peak-normalised to −3 dBFS, denoised at 16 kHz, gain undone |
| `hp300_denoise` | high-pass, then the same |

`band16` is the control that makes the result meaningful: the denoiser only runs at 16 kHz, so without a bandwidth-only arm a confidence drop could not be told apart from the model's own 8 kHz ceiling — the trap experiment 0020 caught. Everything ran on CPU on purpose, in two stages because the denoiser needs torch and the analyzer needs birdnetlib; `NOTES.md` records an upstream bug that makes the documented loader return an untrained model.

### Results

Max species confidence and detection counts:

| arm | regions | captures detected | mean max-conf |
|---|---|---|---|
| `raw` | 10 | 4/4 | 0.865 |
| `hp300` | 7 | 4/4 | 0.884 |
| `band16` | 12 | 4/4 | 0.773 |
| `denoise` | 1 | 1/4 | 0.964 |
| `hp300_denoise` | 3 | 3/4 | 0.412 |

Per capture:

| capture | raw | hp300 | band16 | denoise | hp300_denoise |
|---|---|---|---|---|---|
| 94 | 0.847 | 0.873 | 0.747 | none | 0.183 |
| 95 | 0.855 | 0.893 | 0.727 | none | 0.106 |
| 96 | 0.782 | 0.785 | 0.698 | none | none |
| 97 | 0.975 | 0.986 | 0.920 | 0.964 | 0.947 |

The bandwidth is not what did it: `band16` costs about 0.09 of confidence and keeps all four detections, so bandlimiting to 16 kHz is survivable. The destruction is the denoising itself — what the model removes inside the band it keeps. (Experiment 0003 had rejected an earlier denoiser on the 8 kHz ceiling; that objection was true but not the operative one.)

The denoiser also works only where it is least needed. The single surviving capture, 97, has the highest band SNR of the four at 21.4 dB; the three it erases sit at 19.1, 13.1 and 12.6 dB. The noisy recordings are the entire reason to want a denoiser, and those are exactly where it fails. Even the surviving detection is not the same detection — it relabels capture 97's call from `alarm call`/`call` to `flight call`.

The high-pass wins outright at 0.884 against raw's 0.865, on 4/4 captures — a fifth independent confirmation of experiment 0008 — while reducing region count from 10 to 7 through the fragment-merging 0008 predicted. On capture 94 it collapses three fragmented regions labelled `alarm call` and `call` into one clean `call`.

### Band SNR would have said the exact opposite

| capture | raw | denoise |
|---|---|---|
| 94 | 19.10 | 44.19 |
| 95 | 12.62 | 36.85 |
| 96 | 13.12 | 36.76 |
| 97 | 21.43 | 46.95 |

The denoiser more than doubles band SNR on every capture while erasing three of the four crows. `band_snr` is a 99th-over-10th-percentile ratio, so anything that gates quiet passages toward zero inflates it by construction. Judged on band SNR alone this would have read as a triumph, and it would have been completely wrong.

### Caveats

Four captures, all from one location with one noise source (mowers). These are real field recordings rather than seeded archive audio, but the sample is small and the finding is about the detection pipeline's behaviour under this specific denoiser, not about denoising in general.

### What this changed

- Decided not to adopt biodenoising, and not to fork or package it. The environment stays vendored here so the measurement is reproducible; nothing downstream depends on it.
- A concrete rule was bought: `band_snr` is never sufficient on its own to judge a filter, because it rewards gating. Any future arm that changes the noise floor must also be scored on detections or labels.
- The 300 Hz high-pass case in `FUTURE.txt` is strengthened — a free filter beats a 19M-parameter model — but it stays in `FUTURE.txt` because it changes what every stored analysis means and wants doing alongside a re-analysis.
- The denoising question for the generative route stays open: the BirdDiff note in `FUTURE.txt` concerns learning from the archive corpus, not field detection, and nothing here tests that.
