# 0120 — Does BirdMixIT source separation break the overlapping-crow ceiling on `mob` and `alert`?

**2026-11-23** · GPU (~2 min BirdMixIT) + CPU (BirdNET) · **status: pre-registered, awaiting run**

> **Pre-registration (written and committed before running BirdMixIT on `crow-tools` alarm segments or scoring any classifier).**

## The question

Experiment `0036` (`overlap_wall.py` -> `overlap.json`) identified overlapping crows — not label count and not backbone size — as the bottleneck in the alarm family on the `2,338` keyed `crow-tools` segments:
- **`alert`:** Average precision plunges from **`0.709`** on `one_crow` (`n = 1,793`, balanced accuracy `0.795`) to **`0.365`** on `two_or_more` (`n = 536`, balanced accuracy `0.638`, positive recall `0.404`).
- **`mob`:** Balanced accuracy drops from **`0.743`** on `one_crow` to **`0.701`** on `two_or_more`, where raw AP (`0.867`) sits at just **`1.33×` prevalence (`0.651`)** vs. `2.93×` on `one_crow` — on crowd audio the classifier mostly predicts `"crowd => mob"`.

Experiment `0118` showed that Google Research's pretrained 22.05 kHz **BirdMixIT** 4-source model (`output_sources4`) cleanly separates synthetic `0 dB` 2-crow mixtures (`+4.41 dB` best-stem, `+7.03 dB` partition SI-SDRi) and lifted `0104` hawk posture classification from `0.857` to `0.905`.

This experiment tests whether BirdMixIT earns a place inside `analyzer/` to separate `mob` from `alert` when multiple crows overlap — **under realistic serve-time gating (no human `crowCount` oracle)**, and against an explicit operational cost bar (adding a TensorFlow 1 separator to a CPU worker).

---

## Pre-declared protocol

### Dataset & exact alignment with `0036/overlap_wall.py`

- Exact `2,338` keyed `crow-tools` segments (`1,793` `crowCount == 1`, `536` `crowCount >= 2`, `9` `crowCount == 0`) and flags from `experiments/0036-what-would-more-labels-buy/results/{crowtools_keyed.npz, crowtools_flags.json}`.
- **5-fold recording-grouped cross-validation** (`StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)`, grouped by `groups` = recording `file_id`), matching `overlap_wall.py` byte-for-byte.

### Realistic serve-time crowd gate (zero oracle `crowCount`)

At `analyzer/` inference time, human `crowCount` is unknown. Instead, every 3.0 s window's `1024-d` BirdNET vector (`X[:, :1024]`) is scored **out-of-fold** (on the exact same recording-grouped splits, trained on `crowCount == 1` vs. `crowCount >= 2` as in `0109`) to produce an honest out-of-fold crowd probability `P_several_oof`, with `0113`'s pre-established **`T_single = 0.5826`** cut:
- Windows with `P_several_oof >= 0.5826` ("suspected multi-crow") are routed through **BirdMixIT (`output_sources4`)**.
- We also separate all remaining `crowCount >= 2` windows so the **oracle-gated stratum upper bound** can be reported as a diagnostic secondary alongside realistic gating.

### Separation & BirdNET stem embedding

- For each 3.0 s window `[aligned_start, aligned_start + 3.0 s]` at `22,050 Hz`, run BirdMixIT (`4` waveform stems) and keep the **top 2 stems** by `700–4500 Hz` RMS (`>= 15%` of loudest stem, duplicating stem 1 if only 1 stem clears `15%`, matching `0118`), then embed each stem with BirdNET `2.4` (`1024-d`).

### Pre-declared model arms (compared on identical folds)

Baseline and all arms use `StandardScaler() + LogisticRegression(max_iter=2000, class_weight="balanced")` (`C = 1.0`, identical to `overlap_wall.py`, plus `C = 0.05` reported in secondary check to verify regularization does not alter the conclusion):
1. **Baseline (`unseparated`):** Exact `overlap_wall.py` model on unseparated `1024-d` BirdNET window embeddings (`X[:, :1024]`, matching `X[:, :3072]` since single-window `std = 0` and `max = mean`).
2. **Arm A (`gated_mix_plus_stems` — Primary candidate):** Concatenates `[e_mix (1024d), 0.5 * (e_s1 + e_s2) (1024d), |e_s1 - e_s2| (1024d)]` (`3072-d`) when `P_several_oof >= 0.5826`, and `[e_mix, e_mix, zeros(1024)]` when `P_several_oof < 0.5826` — preserving crowd context while exposing individual separated stem voices and inter-stem contrast.
3. **Arm B (`gated_stem_max_proba` — Zero-width-change ensemble):** Fits a single-voice classifier on `one_crow` windows and scores gated multi-crow windows by `0.5 * P_mix + 0.5 * max(P(e_s1), P(e_s2))` (`mean` for `alert` vs. `max` tested).
4. **Arm C (`oracle_gated_mix_plus_stems` — Diagnostic upper bound):** Same as Arm A but gated by ground-truth `crowCount >= 2`.

### Primary metric & ship bar (fixed now)

- **Primary metric:** Unweighted mean **Average Precision (AP)** across `alert` and `mob` within the **`two_or_more` (`crowCount >= 2`, `n = 536`)** stratum under **Arm A (`gated_mix_plus_stems`, realistic `P_several_oof` gating)** vs. **Baseline (`unseparated`)**, with a 2,000-resample recording-clustered bootstrap 95% CI on `Δ mean_AP`.
- **Co-reported alarm contrast:** Direct `mob` vs. `alert` ROC-AUC & balanced accuracy on `crowCount >= 2` segments flagged exclusively `mob` or `alert`.
- **Ship bar into `analyzer/`:** Because BirdMixIT adds a TensorFlow 1 separator pass to a CPU worker, Arm A (or Arm B) **passes for `analyzer/` integration** iff:
  1. `Δ mean_AP(alert, mob)` on `two_or_more` is **`>= +0.030`** (`+3.0` AP points),
  2. Recording-bootstrap 95% CI of `Δ mean_AP` excludes `0`, and
  3. `one_crow` mean AP across all 5 flags (`alert, begging, softSong, rattle, mob`) drops by **`<= 0.010`**.
  Otherwise BirdMixIT is **not** wired into `analyzer/`'s serving path.
