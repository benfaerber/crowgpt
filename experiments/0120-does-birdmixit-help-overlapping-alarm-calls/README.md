# 0120 — Does BirdMixIT source separation break the overlapping-crow ceiling on `mob` and `alert`?

**2026-11-23** · GPU (~1 min BirdMixIT) + CPU (BirdNET) · **answer: no — under realistic serve-time gating (`P_several >= 0.583`), BirdMixIT lifts `two_or_more` mean `alert`/`mob` AP by only `+0.020` (`95% CI: -0.005 to +0.049` at `C = 1.0`) and `+0.007` (`-0.015 to +0.034` at `C = 0.05`), with direct `mob` vs. `alert` AUC unchanged (`0.790` vs. `0.790`); do not add BirdMixIT to `analyzer/`**

> **Pre-registration (written and committed in `52b3ade` before running BirdMixIT on `crow-tools` alarm segments or scoring any classifier).**

## The question

Experiment `0036` (`overlap_wall.py` -> `overlap.json`) showed that overlapping crows are where `alert` and `mob` degrade on the `2,338` keyed `crow-tools` segments: `alert` AP drops from `0.722` on `one_crow` (`n = 1,793`) to `0.370` on `two_or_more` (`n = 536`), while `mob` balanced accuracy drops from `0.743` to `0.710` (`1.33×` prevalence AP).

Experiment `0118` proved that pretrained 22.05 kHz **BirdMixIT** (`output_sources4`) separates synthetic `0 dB` 2-crow mixtures (`+4.41 dB` single-stem, `+7.03 dB` partition SI-SDRi). This experiment tests whether BirdMixIT earns its operational weight (adding a TensorFlow 1 separator pass to a CPU worker) inside `analyzer/` under **realistic serve-time gating (no human `crowCount` oracle)**.

---

## Pre-declared protocol

- **Dataset & splits:** Exact `2,338` keyed `crow-tools` segments (`1,793` `one_crow`, `536` `two_or_more`, `9` `crowCount == 0`) on `overlap_wall.py`'s 5-fold recording-grouped CV (`StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)`).
- **Serve-time crowd gate (zero oracle leakage):** Out-of-fold `P_several_oof` computed from unseparated `1024-d` BirdNET vectors (`C = 0.05`, matching `0109`), routing windows with `P_several_oof >= 0.5826` (`0113` cut) through BirdMixIT (`678` unique 3 s windows separated across gated + oracle sets; top-2 stems by `700–4500 Hz` RMS embedded with BirdNET `2.4`).
- **Pre-declared ship bar:** `Δ mean_AP(alert, mob)` on `two_or_more` **`>= +0.030`** with recording-bootstrap `95% CI` excluding `0`, and `one_crow` 5-flag mean AP drop **`<= 0.010`**.

---

## Results

Run once (`separate.py` + `run.py` -> `results.json`).
- **Serve-time crowd gate (`P_several_oof >= 0.5826`):** Fired on `541 / 2,338` segments, catching **`65.5%`** (`351 / 536`) of `crowCount >= 2` segments with a **`10.4%`** (`187 / 1,793`) false-gate rate on `one_crow`.

### Summary across arms (`two_or_more` `n = 536`, `one_crow` `n = 1,793`)

| Arm | `two_or_more` `alert` AP | `two_or_more` `mob` AP | `two_or_more` Mean Alarm AP | `Δ Mean Alarm AP` (`95% CI`) | Direct `mob` vs. `alert` `2+` AUC (`n = 423`) | `one_crow` 5-Flag Mean AP | Ship Gate (`>= +0.030`) |
|---|---:|---:|---:|---|---:|---:|---|
| **Baseline (`unseparated`, `C = 1.0`)** | 0.3699 | 0.8684 | **0.6191** | — | 0.7674 | 0.7696 | — |
| **Arm A (`gated_mix_plus_stems`, `C = 1.0`)** | 0.3954 | 0.8831 | **0.6392** | **`+0.0201`** (`-0.0047` to `+0.0494`) | 0.7693 | 0.7767 | **FAIL** |
| **Arm B (`gated_stem_max_proba`, `C = 1.0`)** | 0.3587 | 0.8325 | **0.5956** | `-0.0235` (`-0.0515` to `+0.0041`) | — | 0.7743 | **FAIL** |
| **Arm B (`gated_stem_mean_proba`, `C = 1.0`)** | 0.3611 | 0.8353 | **0.5982** | `-0.0209` (`-0.0501` to `+0.0085`) | — | 0.7726 | **FAIL** |
| Arm C (`oracle_gated`, `C = 1.0`, *diagnostic*) | 0.4591 | 0.8675 | 0.6633 | *(leaks oracle `crowCount >= 2`)* | — | 0.7936 | — |
| **Baseline (`unseparated`, `C = 0.05`)** | 0.4244 | 0.8850 | **0.6547** | — | **0.7898** | **0.8142** | — |
| **Arm A (`gated_mix_plus_stems`, `C = 0.05`)** | 0.4284 | 0.8941 | **0.6613** | **`+0.0066`** (`-0.0153` to `+0.0336`) | **0.7902** | 0.8054 | **FAIL** |

---

## Three things the numbers explain

1. **Simple L2 regularization (`C = 0.05` vs. `C = 1.0`) buys almost twice what BirdMixIT buys, at zero runtime cost:**
   - Tightening `LogisticRegression` from `C = 1.0` to `C = 0.05` on **unseparated** `1024-d` BirdNET vectors lifts `two_or_more` mean alarm AP from `0.6191` to **`0.6547` (`+0.0356`)** and `one_crow` 5-flag mean AP from `0.7696` to **`0.8142` (`+0.0446`)** — outperforming unregularized BirdMixIT (`0.6392`) without running a separator at all.
   - Once `C = 0.05` is used on both sides, BirdMixIT's realistic serve-time gain shrinks to **`+0.0066`** (`95% CI: -0.0153 to +0.0336`), and direct `mob` vs. `alert` AUC on `two_or_more` is flat (`0.7898` vs. `0.7902`).
2. **Why Arm B (`stem_only` probability blending) went negative (`-0.024`):**
   - Scoring separated stems through a `one_crow` model erases the multi-bird acoustic context that distinguishes `mob` from solo calling and exposes BirdMixIT residual artifacts to a classifier trained on clean audio.
3. **Why Oracle Arm C (`0.663` at `C = 1.0`, `0.687` at `C = 0.05`) would have been a trap without Arm A:**
   - In Arm C, the `|e_s1 - e_s2|` block is non-zero *if and only if* human `crowCount >= 2`, handing the classifier the ground-truth human crowd label (`alert` drops in prevalence on crowds while `mob` jumps `0.19 -> 0.65`). Realistic `P_several_oof` gating in Arm A closed that leak.

## What it changed

- **Decision: do NOT wire BirdMixIT into `analyzer/` or the hosted worker.** Keeping `alert` + `mob` folded into `alarm call` in `analyzer/` remains the right call (`0012` + `0036`), and `analyzer/` avoids a heavy TensorFlow 1 runtime dependency for a `+0.007` non-significant difference.
- **Keep `C` regularization in view for `0121`:** `C = 0.05–0.1` materially improves `1024-d` BirdNET logistic heads over `sklearn`'s `C = 1.0` default (`+0.036` to `+0.045` AP across strata).
