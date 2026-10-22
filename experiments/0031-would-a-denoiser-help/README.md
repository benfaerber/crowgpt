# 0031 — Would a denoiser help?

The question the project has cited twice as an exemplar of work that was
measured properly and then lost, finally written down. Prompted by
[biodenoising](https://github.com/earthspecies/biodenoising-inference) (Earth
Species Project, arXiv 2410.03427), a Demucs-based denoiser trained on animal
vocalisations without clean targets.

**No. It erases the crow.** On three of four mower-contaminated captures the
denoiser takes BirdNET from a confident American Crow detection to *nothing at
all*, while the free 300 Hz high-pass already sitting in `FUTURE.txt` beats
every other arm. Not adopted.

## Method

Captures 94–97: four recordings made in front of the apartment with mowers
running, the same set 0008 used, 76 s in total. Five arms, each written as a
48 kHz WAV so the analyzer sees identical containers:

| arm | what it is |
|---|---|
| `raw` | as recorded |
| `hp300` | 4th-order Butterworth high-pass at 300 Hz |
| `band16` | 48k → 16k → 48k resample, **no denoising** |
| `denoise` | peak-normalised to −3 dBFS, denoised at 16 kHz, gain undone |
| `hp300_denoise` | high-pass, then the same |

`band16` is the arm that makes the result mean anything. The model only runs at
16 kHz, so without a bandwidth-only control a confidence drop cannot be told
from the model's own 8 kHz ceiling — the trap 0020 caught when a 2 kHz lowpass
beat a 3 kbps codec.

Two stages, because the denoiser needs torch and the analyzer needs birdnetlib:

    nice -n 19 env CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=8 .venv/bin/python stage1_arms.py
    ../../pipelines/representation/.venv-birdnet/bin/python stage2_analyze.py

Everything runs on CPU on purpose; see `NOTES.md`, which also records an
upstream bug that makes the documented loader return an untrained model.

## Result

Max species confidence, and how many of the four captures were detected at all:

| arm | regions | captures detected | mean max-conf |
|---|---|---|---|
| `raw` | 10 | 4/4 | 0.865 |
| **`hp300`** | **7** | **4/4** | **0.884** |
| `band16` | 12 | 4/4 | 0.773 |
| `denoise` | 1 | **1/4** | 0.964 |
| `hp300_denoise` | 3 | 3/4 | 0.412 |

Per capture:

| capture | raw | hp300 | band16 | denoise | hp300_denoise |
|---|---|---|---|---|---|
| 94 | 0.847 | 0.873 | 0.747 | **none** | 0.183 |
| 95 | 0.855 | 0.893 | 0.727 | **none** | 0.106 |
| 96 | 0.782 | 0.785 | 0.698 | **none** | **none** |
| 97 | 0.975 | 0.986 | 0.920 | 0.964 | 0.947 |

**The bandwidth is not what did it.** `band16` costs about 0.09 of confidence
and keeps all four detections — bandlimiting to 16 kHz is survivable. The
destruction is the denoising itself. 0003 rejected the crow-tools denoiser on
the 8 kHz ceiling, and that objection was true but not the operative one; the
real problem is what the model removes inside the band it keeps.

**It works only where it is least needed.** The single capture that survives is
97, which has the *highest* band SNR of the four at 21.4 dB. The three it erases
sit at 19.1, 13.1 and 12.6 dB. A denoiser whose failures are concentrated on the
noisy recordings is not a denoiser, and the noisy ones are the entire reason to
want one. It also relabels 97's call from `alarm call`/`call` to `flight call`,
so even the surviving detection is not the same detection.

**The high-pass wins outright**, at 0.884 against raw's 0.865, on 4/4 captures.
That is a fifth independent confirmation of 0008, and it does it while *reducing*
region count from 10 to 7 — the fragment-merging 0008 predicted, which matters
because fragmentation is what produced the spurious short "alarm call" segments.
On capture 94 it collapses three fragmented regions labelled `alarm call` and
`call` into one clean `call`.

## Band SNR would have told you the exact opposite

| capture | raw | denoise |
|---|---|---|
| 94 | 19.10 | **44.19** |
| 95 | 12.62 | **36.85** |
| 96 | 13.12 | **36.76** |
| 97 | 21.43 | **46.95** |

The denoiser more than doubles band SNR on every capture while erasing three of
the four crows. `band_snr` is a 99th-over-10th-percentile ratio, so anything
that gates the quiet passages toward zero inflates it by construction — the same
mechanism that puts merged captures at infinity. Judged on band SNR alone this
would read as a triumph, and it would have been a completely wrong answer.

## What it changed

- **Decided not to adopt biodenoising**, and not to fork or package it. The
  environment stays vendored here so the measurement is reproducible; nothing
  downstream depends on it.
- **`band_snr` is never sufficient on its own to judge a filter.** It rewards
  gating. Any future arm that changes the noise floor has to be scored on
  detections or labels as well. This is the concrete rule the experiment bought.
- **Strengthens the 300 Hz high-pass case in `FUTURE.txt`** — now with a direct
  comparison showing the free filter beats a 19M-parameter model. It stays in
  `FUTURE.txt` rather than `TODO.txt` for the original reason: it changes what
  every stored analysis means, so it wants doing alongside a re-analysis.
- **Does not close the denoising question for the generative route.** The
  BirdDiff note in `FUTURE.txt` is about learning from the archive corpus, not about
  field detection, and nothing here tests that. A different question, still open.
