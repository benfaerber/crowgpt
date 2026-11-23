# 0118 — Can unsupervised bird source separation de-mix overlapping crow mobs and uncover masked predator signals?

> **Pre-registration (written and committed 2026-11-22 before downloading BirdMixIT checkpoints or running separation on any recording).**

## The question

Experiments `0036`, `0105`, and `0113` all hit the same acoustic wall: when two or more crows call at once — the defining condition of a mob — envelope peak counters saturate, Perch's advantage vanishes (`0036`: `mob` AP falls from `2.93×` chance on 1 crow to `1.33×` on `2+`), and single-bird filtering (`0113`) has to discard more than half of pure-crow windows.

Google Research's **BirdMixIT** (`output_sources4`, 22.05 kHz) is the standard open-weights unsupervised avian sound separator, trained via Mixture Invariant Training on wild bird recordings. Nobody in this project has tested two stacked questions:
1. **The conspecific cocktail-party gate:** Can BirdMixIT actually separate *two overlapping American Crows* (nearly identical harsh broadband spectra), or does it only separate heterospecific birdsong occupying different frequency bands?
2. **The mobbing question:** If multi-crow mobbing windows in `0103` and `0104` are separated into stems first, do isolated stems carry owl-vs-hawk or perched-vs-flying information that overlapping choruses obscured?

## Pre-declared protocol

### Model

- Pretrained **Google Research BirdMixIT 4-source model** (`bird_mixit_model_checkpoints/output_sources4/model.ckpt-3223090`, 22,050 Hz input -> 4 waveform stems that sum to the mixture), cached under `data/models/bird_mixit/` (`TF_FORCE_GPU_ALLOW_GROWTH=true`).
- *(Fallback contingency declared before fetching: if the upstream GCS checkpoint is unreachable or corrupt, stop and report rather than substituting an untested heuristic.)*

### Stage 0 — Pre-declared Acoustic Gate on Synthetic 2-Crow Mixtures (no `0102`/`0103`/`0104` labels touched)

- **Benchmark set:** Draw **100 synthetic 2-crow mixtures** (fixed `seed=0`) by pairing two 3.0 s windows from **different** `crow-tools` recordings in `0109`'s dataset that are both human-labelled `crowCount == 1` and detected as pure American Crow (`>= 0.25`), each RMS-normalized and summed at **0 dB SNR** (plus 50 mixtures at **+3 dB SNR** as a secondary check) at 22,050 Hz.
- **Metrics:**
  1. **Oracle permutation-invariant SI-SDR improvement (`SI-SDRi`, dB):** For each 2-source ground truth `(s_1, s_2)` and the 4 predicted stems `(y_1..y_4)`, assign each true source to its best distinct stem `(i != j)` maximizing mean `SI-SDR(s_1, y_i) + SI-SDR(s_2, y_j)`, minus the input mixture `SI-SDR(s_k, s_1 + s_2)`. Also report **MixIT partition SI-SDRi** (partitioning the 4 stems into 2 subsets summing to `\hat{s}_1, \hat{s}_2`, which is BirdMixIT's exact training objective).
  2. **Single-bird count-head recovery:** Run BirdNET on the 0 dB mixture and on the top-2 separated stems, and score `0109`'s frozen `count_head.joblib` (`P(several)`). Does separation reduce median `P(several)` compared to the unseparated 2-crow mixture?
- **Gate rule (binding):**
  - **Passes** if median best-stem **or** partition **`SI-SDRi >= 2.0 dB`** across the 100 `0 dB` conspecific 2-crow mixtures.
  - **Fails (measured null)** if both sit `< 2.0 dB`. In that case, **"unsupervised BirdMixIT does not separate conspecific overlapping crow calls"** is the primary conclusion of `0118` (answering `TODO.txt`'s overlapping-crows question with a direct measurement), and Stage 1 results are still computed once and labelled **exploratory post-gate**.

### Stage 1 — Primary Mob De-Mixing Tests (binding if Stage 0 passes; exploratory if Stage 0 fails)

- **Stem selection rule (applied identically to every multi-crow pure window):** Run BirdMixIT on each 3.0 s multi-crow pure window (`P(several) >= T` from `0115`'s frozen `crowgpt_b4` cut). Keep up to the **top 2 stems** by crow-band (`700–4500 Hz`) RMS energy whose energy is at least `15%` of the loudest stem's energy.
- **Co-primary tests (Holm-corrected family of 2):**
  1. **Primary A — De-mixed caw-level Owl vs. Hawk on `0103` dev (`date < 2023-01-01`):** Segment caws (`segment_caws_in_windows`, `extract_caw_44d`) on the kept separated stems of `0103` dev's multi-crow pure windows, and evaluate with `0103`'s exact `eval_caw_cv` (inverse-recording-weighted per-caw ROC-AUC, 5-fold recordist-grouped, `C=0.1`, 400 permutations, `seed=42`), compared directly against unseparated caws from the exact same multi-crow windows. **Passes** if `w_per_caw_AUC >= 0.60` and Holm `perm_p < 0.05`.
  2. **Primary B — De-mixed BirdNET stem embeddings on `0104`'s video set:** Embed kept separated stems (plus already-single-bird pure windows unchanged) with BirdNET (1024d, mean over stems/windows per recording) and run `0104`'s `GroupedTest(C=0.05)` (400 channel permutations) on **(i)** strict `perched` owl vs. `perched` hawk (`36 vs 15`) and **(ii)** non-strict within-hawk `perched` vs. `flying` (`27 vs 21`), reporting paired delta against unseparated `0104` BirdNET.
