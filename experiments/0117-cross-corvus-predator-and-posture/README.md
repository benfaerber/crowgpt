# 0117 — Do predator and posture signals conserve across *Corvus* species once geography is removed?

> **Pre-registration (written and committed 2026-11-22 before reading/coding non-American-Crow archive remarks or scanning their audio).**

## The question

Every clean semantic test from `0103` to `0114` restricted itself to **American Crow**, leaving **6,316** downloaded Xeno-canto and Macaulay Library recordings with non-empty notes across other *Corvus* / corvid species sitting unused in `corvid.db` (`hooded-crow` 3,535, `common-raven` 1,262, `carrion-crow` 638, `eurasian-jackdaw` 565, `rook` 316, `large-billed-crow` 175). European recordists frequently name terrestrial mammals (*fox, cat, dog, badger, marten*) and raptor behaviors (*perched buzzard, goshawk*) that are rare in North American remarks.

In `0102` (Section 4), naive cross-species pooling of mammal scolds vs. avian raptors hit `0.869` BirdNET AUC — and failed its control because **metadata alone scored `0.799`** (European crows dominated mammal scolds while American Crows dominated owl/hawk mobs).

Two designs eliminate that species/continent confound **by construction**:
1. **Zero-shot cross-continental transfer:** Train exclusively on **non-American *Corvus*** (Eurasian species) with per-species feature standardization, and evaluate **zero-shot on American Crow** (`0102` strict archive + `0104` strict video). Because 100% of the test set is one species on one continent, species and geography carry **zero** variance at evaluation.
2. **In-fold species orthogonalization:** In pooled cross-*Corvus* cross-validation, standardize features within each species using training-fold statistics **and** linearly regress species one-hot indicators out of every feature inside each training fold, requiring any passing contrast to beat a `metadata + species` null.

## Pre-declared protocol

### Step 1 — Blind remark coding across non-American *Corvus*

- **Species in scope (`GENUS_CORVUS_NON_AMECRO`):** Downloaded Xeno-canto and Macaulay recordings in `corvid.db` for `hooded-crow`, `carrion-crow`, `common-raven`, `eurasian-jackdaw`, `rook`, and `large-billed-crow` (`slug != 'american-crow'`).
- **Screen & blind coding:** Keyword screen over `rmk` / `mediaNotes` for raptors (owl, eagle-owl, tawny, barn/little/ural/long-eared/short-eared owl, hawk, goshawk, sparrowhawk, buzzard, kite, eagle, white-tailed/golden eagle, falcon, peregrine, kestrel, harrier, hobby, osprey), terrestrial mammals (fox, cat, dog, badger, marten, stoat, weasel, wolf, jackal, mammal), humans, and mobbing/scolding phrasing. Every candidate remark is read **blind to audio and model scores** and coded into:
  - `context`: `owl_mobbing`, `hawk_mobbing`, `mammal_scold`, `human_disturbance`, or `none`
  - `witnessed`: `true` only when the recordist observed the trigger/interaction during the recording (excluding guesses, unseen predators, and passive background species lists)
  - `posture`: `perched`, `flying`, `mixed`, `unknown` (`0103`'s exact rules)
  - `pred_vocal`: `true` if the remark or Xeno-canto `also` lists the predator calling.
- Freeze `labels.json` before extracting any audio window.

### Step 2 — Pure-corvid BirdNET & Perch 2.0 window extraction

- Run BirdNET (`min_conf=0.05`, CPU) and Perch 2.0 (`perch_v2`, 1536d, `TF_FORCE_GPU_ALLOW_GROWTH=true`) on every witnessed non-American *Corvus* recording.
- **Strict pure-corvid window rule (matching `0103`):** Target *Corvus* species (or BirdNET corvid where Carrion/Hooded split occurs, per `0089`) detected at `>= 0.25`, **zero non-corvid species `>= 0.05` in the window**, `pred_vocal == False`, and **zero BirdNET raptor/owl detections `>= 0.05` anywhere in the recording**.

### Step 3 — Co-primary tests (Holm-corrected as a family of 3)

1. **Primary A — Zero-shot Eurasian *Corvus* → American Crow (`owl_mobbing` vs. `hawk_mobbing`, strict):**
   - Train `LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced")` on per-species z-scored **BirdNET 1024d** pure-corvid window means across strict Eurasian *Corvus* owl/hawk recordings (requires `>= 10` owl and `>= 10` hawk Eurasian recordings; otherwise declared underpowered).
   - Score **zero-shot** (no refitting) on `0112`/`0102`'s strict American Crow owl/hawk archive recordings (z-scored across the American Crow set without using labels), evaluated by ROC-AUC, two-sided Mann–Whitney `p`, and 2,000-resample recordist bootstrap 95% CI.
   - **Passes** if `AUC >= 0.65`, CI excludes `0.5`, and Holm `p < 0.05`.
2. **Primary B — Species-deconfounded Avian Raptor (`owl` + `hawk`) vs. Terrestrial Mammal (`mammal_scold`) across all *Corvus*:**
   - Combine strict witnessed Eurasian *Corvus* + American Crow (`0102`) recordings. Inside each fold of 5-fold recordist-grouped `StratifiedGroupKFold(seed=0)`, z-score within species using training-fold statistics (falling back to global training stats if `< 3` training rows in a species) **and** regress out one-hot species indicators before fitting `LogisticRegression(C=0.05, balanced)`.
   - Compute `metadata + species` null (`species` one-hot + `lat, lng, duration_s, pure_corvid_frac`) under the same folds after the same species-residualization check (plus raw unresidualized metadata AUC to show the confound size).
   - **Passes** if BirdNET `AUC >= 0.65`, Holm-adjusted 400-shuffle **within-species** recordist permutation `p < 0.05` (labels permuted across recordists *within each species* so species marginals are invariant!), and `AUC` exceeds the residualized density/metadata null by `>= 0.05`.
3. **Primary C — Cross-*Corvus* strict Perched Owl vs. Perched Hawk:**
   - Combine strict `perched` Eurasian *Corvus* recordings with strict `perched` American Crow archive recordings (`0116`). Same within-fold species z-scoring + species-indicator orthogonalization, 5-fold recordist-grouped ROC-AUC, and **400 within-species recordist permutations**.
   - **Passes** if `AUC >= 0.65`, Holm `perm_p < 0.05`, and beats the density null by `>= 0.05`.

### Pre-declared secondary tests

1. **S1 — Perch 2.0 (1536d)** on all three primaries (A, B, C) to verify representation independence.
2. **S2 — Cross-*Corvus* within-hawk Perched vs. Flying** (species-deconfounded CV + zero-shot Eurasian *Corvus* perched-vs-flying → `0104` American Crow hawk videos!).
3. **S3 — Per-species breakdown** for every species with `>= 8` recordings on each side of a contrast.
