# 0119 — Do crow calls predict what happens next?

**2026-11-22** · CPU · **status: pre-registered, awaiting run**

> **Pre-registration (written and committed before scanning candidate windows, forming transition labels, or computing any rate or AUC).**

## The question

Experiments `0102`–`0118` tested **simultaneous** scene labels — what predator, posture, or context a human observer noted during a recording — and found that predator species nouns (`owl` vs. `hawk`) sit at chance once posture is held fixed (`0.35–0.62`), while threat posture (`perched` vs. `flying`, `0.81–0.905`) and broad behavioral context (`0.65–0.80`) are readable.

As `TODO.txt` (*"Nothing can record what a call achieved"*) points out, simultaneous tags cannot test **pragmatics** — what changed *after* a call:
1. **Recruitment:** When a single crow calls with no crowd present, does anything in its call predict that a multi-bird crowd arrives over the next 18 seconds?
2. **Abrupt cessation / scatter:** Inside the same recording and microphone, does the final single-bird call before `>= 15 s` of verified live-mic silence differ acoustically from an earlier single-bird call followed by continued calling — *beyond* simple loudness/SNR fade as a bird moves away from the microphone?
3. **Parental intervention / begging cessation (Capture 104 hypothesis):** Capture 104 (`field.db` `id = 104`) recorded a fledgling begging, an adult calling once (begging continued), and the adult calling a second time ("harder"), after which begging stopped for the remaining 13.5 s of the file. Across hundreds of begging recordings in `corvid.db`, do interspersed non-begging adult calls precede begging cessation above baseline, and does the adult call's acoustics predict whether begging stops vs. continues?

All three questions generate their own time-locked `before -> focal call -> after` labels directly from the `22,768` BirdNET-analyzed American Crow recordings already on disk in `data/corvid.db`, requiring zero new fieldwork.

---

## Pre-declared protocol

### Corpus pool, deduplication, and observer grouping

- **Eligible files:** Downloaded, analyzed `american-crow` recordings in `data/corvid.db` with verified audio duration **`24.0 s <= duration <= 300.0 s`** that contain at least one corvid detection in `detections` (`<= 300 s` prevents multi-hour unattended recorders from dominating compute or fold structure).
- **Deduplication:** Recordings are deduplicated by `content_sha256` (keeping lowest `recordings.id`) so cross-posted files never enter twice.
- **Observer grouping:** All cross-validation folds, bootstraps, and label permutations group strictly by `observer = group_key or normalized_recordist or f"rec:{id}"`.

### Window scan and live-mic tail gate

Every candidate recording in the timestamp-eligible pools is scanned on a non-overlapping **3.0 s grid** (`WindowScanner` as in `0112`, `min_conf = 0.05`, reusing `0112`'s cached BirdNET detections/embeddings where available) alongside 22,050 Hz waveform envelope statistics per 3.0 s window:
- `corvid`, `american_crow`, `raptor`, `other`, and `embedding` (`1024-d` BirdNET vector).
- `rms_db` (broadband dBFS), `crow_rms_db` (`700–4500 Hz` bandpass dBFS), `noise_p10_db` (10th-percentile 50 ms frame dBFS inside the 3 s window), `snr_db = crow_rms_db - noise_p10_db`, `duty_u` (`0107`'s `700–4500 Hz` duty cycle scaled per recording), and `zero_frac` (fraction of samples with `|x| < 1e-5`).

**Live-mic tail gate (`live_tail(t0, t1)`):** Any post-call observation span `[t0, t1]` is valid iff:
1. `t1 <= file_duration - 1.0 s` (safety margin before EOF),
2. Every 3.0 s window in `[t0, t1]` has `zero_frac < 0.05` (no digital silence, truncation, or mute), and
3. `median(noise_p10_db in [t0, t1])` lies within **`[-6.0 dB, +6.0 dB]`** of the recording's pre-focal `noise_p10_db` median (rejecting fade-outs, gain cuts, and mic shutoffs).

### Frozen reference heads and thresholds (fixed before touching `0119` windows)

1. **Crowd head (`P_several`):** `0109`'s frozen `count_head.joblib` (`data/experiments/0109-crow-count/count_head.joblib`).
   - **Single-bird cut (`T_single`):** `0113`'s pre-established 90% one-crow precision cut (`P_several < 0.583`).
   - **Multi-crow arrival cut (`T_crowd`):** Fixed on `0109`'s out-of-fold scores alone as the smallest threshold achieving **`>= 80.0%` `several`-crow precision** on `0109`'s hand-labelled segments (falling back to `0.85` max OOF quantile if 80% is unreachable; computed before scoring any `0119` window).
2. **Begging head (`S_beg`):** `0111`'s frozen `FrozenBeggingHead` (trained on `0102`'s witnessed archive recordings).
   - **Active begging cut:** `S_beg >= 0.0` (the `1.0%` winter false-alarm boundary in `0111`), with `S_beg >= T_beg` (`-2.00`, `0111`'s 90%-recall archive boundary) used as the sensitive detector for post-call residual begging so lingering faint begging is not miscalled "stopped".
   - **Strict non-begging adult call cut:** `S_beg < T_beg` (`-2.00`), ensuring an interspersed adult window is acoustically non-begging rather than a mislabelled begging tail.

---

### Co-primary tests (Holm–Bonferroni corrected as one family)

Any primary with at least **20 events per class** enters the Holm family; any test below 20 per class is reported as underpowered and leaves the family (as in `0110`). Every discriminative test uses `StandardScaler() + LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000)` in **5-fold observer-grouped cross-validation (seed 0)**.

#### Primary A — Single-Bird Recruitment (`Solo -> Crowd` vs. `Solo -> Solo`)
- **Eligibility (at most 1 earliest focal window `[t, t+3]` per recording):**
  - Pre-span `[max(0, t - 9), t]` (`t >= 6.0 s`, `>= 2` windows): zero multi-crow windows (`all crow windows have P_several < T_single`) and `raptor < 0.05`.
  - Focal window `[t, t + 3]`: strict pure single-crow window (`american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05`, `P_several < T_single`).
  - Post-span `[t + 6, t + 24]` (`18 s` after a 3 s guard `[t + 3, t + 6]`, passing `live_tail(t + 3, t + 24)`):
    - **`recruited` (`y = 1`):** `>= 2` crow windows (`corvid >= 0.25`) in `[t + 6, t + 24]` have `P_several >= T_crowd`.
    - **`unrecruited` (`y = 0`):** Zero windows in `[t + 3, t + 24]` have `P_several >= T_single` (capped at random `seed = 0` to at most `4 × n_recruited` negative recordings if negatives exceed `4×`, keeping CV fast while preserving full positive power).
- **Binding metric:** Out-of-fold ROC-AUC on focal BirdNET `1024-d` embeddings **with `[P_several, duty_u, crow_rms_db, snr_db]` regressed out inside each training fold** (blocking faint pre-existing background crowd or loudness leakage), tested with **400 observer-level label permutations**.
- **Pass bar:** Residualized ROC-AUC **`>= 0.65`** and Holm-adjusted `perm_p < 0.05`.

#### Primary B — Within-Recording Abrupt Cessation / Scatter (`Continuing` vs. `Terminal` Single-Bird Call)
- **Eligibility (strictly 1 matched pair `[t_cont, t_stop]` per recording):**
  - Terminal focal window `[t_stop, t_stop + 3]`: pure single-crow window (`american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05`, `P_several < T_single`), followed by `[t_stop + 3, t_stop + 18]` (`15 s`) passing `live_tail(t_stop + 3, t_stop + 18)` with **zero** corvid detections (`max corvid < 0.10`) and **mean `duty_u < 0.05`** (verifying genuine acoustic silence rather than missed faint caws).
  - Paired earlier continuing window `[t_cont, t_cont + 3]` in the **exact same recording** (`t_cont <= t_stop - 12.0 s`): pure single-crow window (`american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05`, `P_several < T_single`) followed by **`>= 2` crow windows** (`corvid >= 0.25`) in `[t_cont + 3, t_cont + 18]`. (If multiple `t_cont` qualify, choose the one closest in `snr_db` — or earliest before `t_stop - 12 s`; **fixed now: choose the earliest qualifying `t_cont`**, so loudness differences are observed honestly first in `S_B1` rather than hidden by selection, and then regressed out in the primary!)
- **Binding metric:** 5-fold observer-grouped ROC-AUC (both members of every pair stay in the same fold) on BirdNET `1024-d` embeddings **with `[crow_rms_db, snr_db, P_several, duty_u]` regressed out inside each training fold**, tested against **400 within-recording sign-flip permutations** (randomly swapping `continuing` and `terminal` inside each recording).
- **Pass bar:** Residualized ROC-AUC **`>= 0.65`** and Holm-adjusted paired sign-flip `perm_p < 0.05`.

#### Primary C — Parental Call Acoustics Before Begging Cessation (Capture 104 Hypothesis)
- **Eligibility (interspersed non-begging calls during active begging):**
  - Recording contains verified begging (`>= 2` windows with `corvid >= 0.25` and `S_beg >= 0.0`).
  - At focal window `[t, t + 3]` (`t >= 9.0 s`, `live_tail(t + 3, t + 18)` valid):
    - Pre-span `[max(0, t - 12), t]` has active begging (`>= 2` crow windows with `S_beg >= T_beg`, at least one `>= 0.0`).
    - Focal window `[t, t + 3]` is a **strict non-begging crow window**: `american_crow >= 0.25`, `raptor < 0.05`, and **`S_beg < T_beg`** (`-2.00`).
    - Post-span `[t + 3, t + 18]` (`15 s`):
      - **`begging_stopped` (`y = 1`):** Zero windows in `[t + 3, t + 18]` have `corvid >= 0.15` with `S_beg >= T_beg`.
      - **`begging_continued` (`y = 0`):** `>= 2` windows in `[t + 3, t + 18]` have `corvid >= 0.25` with `S_beg >= T_beg`.
    - Capped at **1 event per `(recording, outcome)`** (earliest `stopped = 0` and earliest `stopped = 1` if both occur in the same recording, as in Capture 104!), grouped by observer across folds.
- **Binding metric:** 5-fold observer-grouped ROC-AUC on focal BirdNET `1024-d` embeddings **with `[crow_rms_db, snr_db, P_several, S_beg]` regressed out inside each training fold**, tested with **400 observer-level permutations**.
- **Pass bar:** Residualized ROC-AUC **`>= 0.65`** and Holm-adjusted `perm_p < 0.05`.

---

### Pre-declared secondary & diagnostic checks

1. **`S_leak` (Confound / Fade Audits for A, B, C):**
   - Report raw (unresidualized) BirdNET `1024-d` AUC alongside the nuisance-only AUC (`[P_several, duty_u, crow_rms_db, snr_db]`).
   - **`S_B1` (The "Bird Flew Away" test on Primary B):** Paired Wilcoxon signed-rank test on `snr_stop - snr_cont` and `crow_rms_stop - crow_rms_cont` within the same recording — directly measuring whether terminal calls before silence are quieter than continuing calls.
2. **`S_caw44` (Interpretable Single-Caw Prosody & Spectrum):**
   - Run `0103`'s `segment_caws_in_windows` + `extract_caw_44d` (amplitude-normalized per caw) on the focal windows of Primaries A, B, and C to test whether caw duration, F0, pitch slope, or attack sharpness move before recruitment, silence, or begging cessation.
3. **`S_C1` (Event-Rate / Hazard Test — Do Adult Calls Stop Begging Above Baseline?):**
   - Across active-begging checkpoints `[t, t + 3]` with `live_tail(t + 3, t + 18)`, compare empirical begging-cessation rate `P(begging_stopped)` after an **interspersed non-begging crow window** (`S_beg < T_beg`) vs. after an **ongoing begging window** (`S_beg >= 0.0`), with a 2,000-resample observer-clustered bootstrap 95% CI on the rate difference `Δp` (plus linear control for normalized recording position `t / duration` so end-of-bout timing cannot masquerade as adult suppression).
4. **`S_104` (Out-of-Sample Capture 104 Walk):**
   - Score Capture 104 (`field.db` `id = 104`, excluded from all `0119` fitting) across its 3 s windows (`0..63 s`) and report `S_beg`, `P_several`, `snr_db`, and the corpus-trained Primary C adult-cessation score on the two adult-call regions (`~27 s` vs. `42–51 s`).
