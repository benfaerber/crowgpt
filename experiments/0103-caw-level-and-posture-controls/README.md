# 0103 — Does owl vs. hawk mobbing survive caw-level segmentation, all-species bystander masking, and predator posture control?

> **Pre-registration notice (written before running any C, D, or E classifier or viewing any results):**
> All primary feature sets, primary metrics, masking rules, controls, and the temporal holdout cutoff (`2023-01-01`) below were fixed *before* extracting features, coding posture, or running any model. Any additional feature set or diagnostic reported later is explicitly labelled **exploratory**.

## Questions

Experiment `0102` established a recording-level owl-vs-hawk difference (`0.769` ROC-AUC on strict zero-raptor recordings), but an independent audit identified three unresolved confounds:
1. **Recording-level chorus vs. single caw:** `0102` pooled whole recordings, where chorus density (`crow_frac`, duty cycle, duration) alone scored `0.72`. Does an **individual segmented crow caw** carry owl vs. hawk information?
2. **Unmasked bystander species:** `0102` masked only raptors (`conf >= 0.05`), leaving woodland owl-mob bystanders (Blue Jays, Steller's Jays, chickadees, songbirds) unmasked inside 3s BirdNET windows.
3. **Predator posture confound:** Owls are almost always mobbed while perched, whereas hawks are often mobbed in flight. Does owl vs. hawk survive when restricted strictly to **perched** predators in the Xeno-canto + Macaulay archive?

## Pre-declared protocol

### Step E — Untouched temporal holdout (locked first in `holdout_2023.json`)
- **Cutoff:** Every strict zero-raptor American Crow `owl_mobbing` / `hawk_mobbing` recording in `0102/labels.json` with recording date **`>= 2023-01-01`** is sealed untouched (`n = 42`: 18 owl, 24 hawk). All cross-validation, matching, and diagnostics run strictly on **`date < 2023-01-01`** (`n = 106`: 61 owl, 45 hawk).
- **Single-shot test:** Final models from C and D are fit once on `date < 2023-01-01` and evaluated **exactly once** on `date >= 2023-01-01` at the end.

### Step C — Caw-level owl vs. hawk with all-non-crow masking
- **Strict pure-crow masking rule:** Keep only 3s BirdNET windows (`min_conf = 0.05`) where American Crow (`American Crow` / `Northwestern Crow`) is detected at `conf >= 0.25` **and zero non-crow species** are detected anywhere in that 3s window at `conf >= 0.05` (masking every raptor, jay, songbird, human, and other non-crow species). Recordings must also satisfy `pred_vocal = false` and `max_raptor_conf < 0.05` everywhere.
- **Individual caw segmentation:** Deterministic crow-band (`700–4500 Hz`, 22050 Hz) RMS envelope peak finder inside pure-crow windows (min spacing `180 ms`, prominence `>= 0.15`, onset/offset at `25%` peak height, duration `80–700 ms`, up to 30 highest-SNR caws per recording).
- **Pre-declared primary feature set:** `caw_acoustic_44d` — 44 per-caw waveform features extracted strictly inside `[onset, offset]` on unit-RMS peak-normalized `600–5000 Hz` audio (duration, attack fraction, peak/mean RMS, YIN F0 median/IQR/slope/voiced fraction, spectral centroid/std/bandwidth/rolloff/flatness/ZCR, harmonic ratio, low-mid ratio, 13 MFCC means + 13 MFCC stds, 3 sub-band energy ratios). Zero recording-level density, duration, or BirdNET context features.
- **Pre-declared primary metric:** **Inverse-recording-weighted per-caw ROC-AUC** (`StandardScaler` + `LogisticRegression(C=0.1, solver="liblinear", class_weight="balanced")`) under **5-fold `StratifiedGroupKFold` holding out whole recordings by recordist**, evaluated on:
  1. Full pure-crow dev set (`date < 2023-01-01`), with 400-shuffle recordist-level permutation test and metadata-only null (`duration_s`, `lat`, `lng`, `month_sin/cos`, `hour_sin/cos`, `source`).
  2. 1-to-1 **density-matched** dev subset (matched on recording `crow_frac`, `duty_cycle`, and `n_pure_crow_windows`).
- **Explicitly exploratory diagnostics:** (i) Unweighted per-caw AUC & recording-averaged caw AUC; (ii) `birdnet_isolated_caw_1024d` (isolated `[onset-20ms, offset+20ms]` caw zero-padded to 3.0s with 10 ms fades); (iii) recording-level BirdNET mean embedding on strictly pure-crow windows (testing whether bystander masking alone eliminates 0102's 0.769).

### Step D — Archive predator posture control (`perched` vs. `flying`)
- **Blind remark coding:** Re-read every strict owl/hawk remark in `0102/labels.json` (`n = 148`, blind to audio and split) and code predator posture into `perched`, `flying`, `mixed`, or `unknown` (`posture_labels.json`).
- **Pre-declared primary subset:** Strictly `posture == "perched"` + zero-raptor + pure-crow windows (`date < 2023-01-01`).
- **Pre-declared primary feature set & metric:** **Recording-level BirdNET mean embedding (1024d) on strictly pure-crow windows, 5-fold recordist-grouped ROC-AUC** (`StandardScaler` + `LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced")`) with 400-shuffle recordist-level permutation test and metadata-only null.
- **Explicitly exploratory diagnostics:** Caw-level `caw_acoustic_44d` restricted to `perched` dev clips, and `perched` vs. `flying` within `hawk_mobbing`.

---

## Results

*(Pending execution — will be filled in strictly after C, D, and one-shot E complete.)*
