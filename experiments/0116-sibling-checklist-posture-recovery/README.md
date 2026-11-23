# 0116 — How many unknown raptor postures do sibling eBird checklists recover, and does perched owl vs. hawk move?

> **Pre-registration (written and committed 2026-11-22 before fetching any checklist or viewing any sibling comment).**

## The question

Experiment `0103` showed that predator posture severely confounds archive owl-vs-hawk comparisons (`16:2` perched for owls vs. `12:18` perched:flying for hawks), and left the perched-only test underpowered (`n = 28` strict archive recordings total: `20` dev -> `0.490` AUC, `6` holdout -> `0.500` AUC) because **89 of 148** strict American Crow remarks did not state what the predator was doing (`unknown`). Experiment `0104` built a 310-video set and also landed underpowered (`36` perched owl vs. `15` perched hawk -> `0.539` AUC), while finding **perched vs. flying within hawk at `0.857`**.

However, **137 of `0103`'s 148** strict Macaulay recordings (and ~235 of `0102`'s 257 witnessed American Crow owl/hawk recordings) carry an `ebirdChecklistId` (`S...`) in `corvid.db`. On eBird checklists, observers often write what the hawk or owl was doing under **the raptor's own checklist row** or the **checklist-level comments**, neither of which is copied into the American Crow audio's `mediaNotes`.

This experiment pulls the official eBird v2 checklist records for those `S...` checklists, blind-codes predator posture from the sibling raptor observations before touching any audio or score, and re-tests perched owl vs. perched hawk at the enlarged sample size.

## Pre-declared protocol

### Step 1 — Checklist fetch & blind text extraction

- **Scope:** Every witnessed American Crow `owl_mobbing` or `hawk_mobbing` recording in `0102/labels.json` that carries an `ebirdChecklistId` in `corvid.db`.
- **Source:** Official eBird API v2 (`https://api.ebird.org/v2/product/checklist/view/{subId}`) via `EBIRD_API_KEY`, rate-limited politely (`<= 4 req/s`), raw JSON cached under `data/experiments/0116-checklist-posture/checklists/` (gitignored).
- **Blind coding sheet:** Extract only `(recording_id, checklist_comments, raptor_obs_comments_and_breeding_codes)` with **no audio features, no model scores, and no recording dates or splits shown**.

### Step 2 — Blind posture & vocal-raptor coding rules (frozen before scoring)

- **Codebook (identical to `0103`):**
  - `perched`: text explicitly places the predator perched, sitting, roosting, or stationary in a tree/snag/branch/wire/pole/roof/ledge without flying.
  - `flying`: text explicitly places the predator flying, soaring, circling, gliding, stooping, or chased in flight without perching.
  - `mixed`: predator observed both perched and flying (e.g., *"perched in pine then flushed and chased"*).
  - `unknown`: posture still unstated or ambiguous.
- **Preservation of `0103` coding:** Recordings already coded `perched`, `flying`, or `mixed` in `0103/posture_labels.json` keep their `0103` posture unless the sibling raptor comment explicitly reveals the opposite posture occurred too (in which case upgrading to `mixed` is logged; an exploratory sensitivity arm also holds `0103`'s original 59 non-unknown labels completely untouched).
- **Vocal-raptor hygiene (`pred_vocal_checklist`):** If the sibling raptor comment states the owl or hawk was calling/hooting/screaming/vocalizing (`pred_vocal_checklist = true`), that recording is **excluded** from the strict zero-raptor set (tightening `0103`'s strictness, never loosening it).
- `checklist_posture_labels.json` (ids and discrete codes only; free text stays under `data/`) is written and frozen **before** `eval.py` runs.

### Step 3 — Primary and secondary tests

- **Audio & pure-crow windows:** Reuse `0112`'s single BirdNET scan (`sets.WindowTable`, `pure()` = `american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05`, plus recording-level `max_raptor_conf < 0.05`, `pred_vocal == False`, `pred_vocal_checklist == False`).
- **PRIMARY — Enlarged strict archive Perched Owl vs. Perched Hawk:**
  - Feature & model (matching `0103` Step D & `0104`): recording-level **BirdNET mean embedding (1024d)** over pure-crow windows, `StandardScaler` + `LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced")`, **5-fold `StratifiedGroupKFold` grouped by recordist**, out-of-fold ROC-AUC, **400-shuffle recordist-level permutation test** (`seed=42`), beside the density null (`duration_s`, `pure_crow_frac`, `n_pure_crow_windows`, `C=0.5`).
  - **Pass rule:** Both classes `>= 15` (reported as underpowered if `< 50`, uninterpretable if `< 15`); passes as evidence of predator-specificity if `AUC >= 0.65`, `perm_p < 0.05`, and `AUC - AUC_density_null >= 0.05`.
- **Secondary, declared now (Holm-corrected across S1–S3):**
  1. **S1 — Perch 2.0 (1536d) and CrowGPT block 4** (`0112` cached window means) on the exact same enlarged strict archive perched set.
  2. **S2 — Within-hawk Perched vs. Flying in the archive** (strict and non-strict pure-crow windows, BirdNET & Perch), testing whether `0104`'s `0.857` video posture contrast replicates in audio-only archive checklists.
  3. **S3 — Pooled strict Perched Owl vs. Perched Hawk across Archive (`0116`) + Video (`0104`):** Combining `0116`'s strict perched archive recordings with `0104`'s strict perched video clips (`36 owl / 15 hawk`, channel-capped at 2), 5-fold group-stratified CV (recordist / channel), with dataset source (`archive` vs. `video`) regressed out of every embedding dimension inside each training fold so domain differences cannot leak class priors.
