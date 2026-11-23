# 0115 — Does single-bird bout syntax or phrase trajectory carry predator or context information?

**2026-11-22** · CPU · **answer: no — both co-primaries are null: single-bird bout syntax scores 0.353 on owl vs. hawk (Holm p = 1.0), and shuffling caw order inside every bout changes 5-context AUC by −0.007 (0.581 real vs. 0.587 shuffled, Holm p = 1.0)**

> **Pre-registration (written and committed in `437b51c` before extracting any bout feature or running any classifier).**

## The question

Experiments `0103` and `0112` showed that an **isolated single caw** carries no owl-versus-hawk information across 44 waveform features (`0.516`), BirdNET (`0.522`), Perch (`0.546`), or CrowGPT Dual-AR (`0.430`). Experiment `0113` showed that averaging graded caw features across single-bird windows reads five contexts modestly (`0.665`) and owl-versus-hawk weakly (`0.610`). Meanwhile `0114` fed raw 6 s EnCodec chunks to CrowGPT and found three quarters of the scene bits lived in fine-stage timbre/channel and crowd size.

What none of these tested is **phrase structure and sequential order within a single bird's calling bout** — caws per burst, inter-caw interval (ICI) cadence, acceleration or deceleration across a burst, and how duration and pitch evolve from the first caw of a phrase to the last. In Yorzinski & Vehrencamp (*Condor*, 2009) on American Crows and Templeton et al. (2005) on chickadees, threat urgency and predator danger are encoded in **bout delivery and pacing** rather than noun-like single-syllable timbre.

## Pre-declared protocol

### Recordings and upgraded single-bird cut

- **Recordings:** The 423 witnessed American Crow archive recordings in `0112`'s `ArchiveSet` (`raptor_mobbing`, `begging`, `roost_gathering`, `food_foraging`, `flight_contact`), using `0112`'s cached BirdNET 3 s windows (`american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05` — `0103`'s strict pure-crow rule).
- **Single-bird gate (upgraded to `0112`'s best counter, fixed before scoring archive windows):** Fit `StandardScaler` + `LogisticRegression(C=0.05, class_weight="balanced")` on `0112`'s `CrowdInsideType` segments using **CrowGPT Dual-AR block 4** embeddings (`0.845` within-type AUC in `0112`, vs. BirdNET's `0.806`). Compute out-of-fold `P(several)` on those hand-labelled segments and fix `T` as the largest threshold achieving `>= 90.0%` one-crow precision. Keep strictly pure-crow archive windows with `crowgpt_b4` `P(several) < T`.
- **Contiguous span merging & bout segmentation:** Merge adjacent single-bird pure windows (`start_{k+1} - start_k == 3.0 s`) into contiguous single-bird spans before running `0103`'s `segment_caws_in_windows(..., max_caws=10_000)` at 22,050 Hz, so bouts crossing a 3 s boundary are not cut in half. Consecutive segmented caws inside a contiguous span with onset-to-onset interval `<= 1.50 s` form a **bout**. A recording enters if it has at least **3 single-bird caws** and at least **1 multi-caw bout (`>= 2` caws)**.

### Channel-blind, timbre-free bout representation (`bout_syntax_28d`)

Zero MFCCs and zero spectral-envelope/channel features are included. Every caw supplies only 5 prosodic scalars from `0103`'s `extract_caw_44d`: `caw_dur_s` (idx 0), `attack_frac` (1), `peak_to_mean_rms` (2), `f0_med_hz` (3), and `f0_slope_hz_s` (5), plus onset/offset times.

1. **Order-invariant cadence & burst block (`cadence_10d`):**
   - Caws per bout (mean, std, max over all single-bird bouts including singletons), fraction of caws in multi-caw bouts, multi-caw bout duration (mean), intra-bout ICI (mean, median, IQR, CV), and inter-bout gap `<= 10 s` (median, `0` if `< 2` bouts within a contiguous span).
2. **Order-dependent trajectory & transition block (`order_18d`, over bouts with `>= 2` caws):**
   - Within-bout linear slope vs. normalized caw index `0..1` (mean & std across multi-caw bouts) for each of the 5 caw scalars (`10d`).
   - Last-minus-first caw delta (`x_last - x_first`, mean across multi-caw bouts) for `caw_dur_s`, `f0_med_hz`, and `attack_frac` (`3d`).
   - Adjacent-step signed step `mean(x_{t+1} - x_t)` and step magnitude `mean(|x_{t+1} - x_t|)` for `caw_dur_s` and `f0_med_hz` (`4d`), plus rhythmic acceleration `mean(log((ICI_{t+1} + 1e-3) / (ICI_t + 1e-3)))` on bouts with `>= 3` caws (`0` if none; `1d`).

### Co-primary tests (Holm-corrected as a family of 2)

1. **Primary A — Strict single-bird Owl vs. Hawk from `bout_syntax_28d`:**
   - Subset: strict zero-raptor `owl_mobbing` vs. `hawk_mobbing` (`pred_vocal == False`, `max_raptor_conf < 0.05`).
   - Model & metric: `StandardScaler` + `LogisticRegression(C=0.1, class_weight="balanced", max_iter=3000)`, **5-fold `StratifiedGroupKFold` grouped by recordist (seed 0), ROC-AUC**, with a **400-shuffle recordist-level permutation test**.
   - **Passes** if ROC-AUC `>= 0.65` and Holm-adjusted `perm_p < 0.05`.
2. **Primary B — Within-bout caw-order shuffle test (`order_18d`):**
   - Across all eligible 5-context archive recordings, evaluate 5-context macro OvR ROC-AUC (`GroupedOvR`, `C=0.1`, 5-fold recordist-grouped) on `order_18d` computed on the **true temporal order** of caws inside each bout, vs. **200 within-bout permutations** where the caw scalars and ICIs inside each multi-caw bout are randomly reordered (preserving every bout's exact marginal distribution of durations, pitches, and ICIs while destroying sequential order).
   - **Passes** if `AUC_real - mean(AUC_shuffled) >= 0.03` and Holm-adjusted empirical shuffle `p = (hits + 1) / 201 < 0.05`.

### Pre-declared secondary tests

1. **S1 — Five-context macro AUC & crowd control:** Full `bout_syntax_28d` and `cadence_10d` vs. `0113`'s 47d bag-of-caws features on the exact same eligible recordings, both raw and with the recording's mean `crowgpt_b4` count score regressed out inside each fold (`Residualised`).
2. **S2 — Within-owl species contrast (Great Horned Owl vs. Barred Owl, single-bird):** Testing whether `0102`'s `0.773` prosody AUC between Great Horned and Barred Owl mobs survives single-bird gating (`bout_syntax_28d`, 5-fold recordist-grouped ROC-AUC + 400 permutations, using `trigger` from `0102/labels.json`).
3. **S3 — Within-recording temporal phase ("scout/onset" first 15 s vs. "sustained" > 15 s):** Paired sign/Wilcoxon test on raptor-mobbing recordings that have single-bird bouts in both `[0, 15] s` and `(15, 300] s`, testing whether early calls differ in ICI, caw duration, or pitch from sustained mobbing calls on the same microphone.
4. **S4 — Within-bout order shuffle on Owl vs. Hawk specifically** (`order_18d`, real vs. 200 within-bout shuffles).

---

## Results

Run once (`results.json`).
- **Upgraded one-crow cut (`crowgpt_b4`):** Out-of-fold `P(several) < 0.652` kept **1,897 of 2,479** hand-labelled `crow-tools` segments at **90.04% one-crow precision** and **89.75% one-crow recall** (up from `0113`'s 87.9% recall under BirdNET). Applied to the archive, **2,282 of 4,603** pure-crow windows passed as single-bird, yielding **239 recordings across 153 recordists** with `>= 3` single-bird caws and `>= 1` multi-caw bout (`raptor_mobbing` 160, `begging` 28, `food_foraging` 26, `roost_gathering` 13, `flight_contact` 12).

### Co-primary results — both NULL

| Co-primary test | Scope | Observed | Null / Shuffle | Holm `p` | Verdict |
|---|---|---:|---:|---:|---|
| **Primary A:** Strict single-bird Owl vs. Hawk (`bout_syntax_28d`) | 88 recs (50 owl / 38 hawk), 72 recordists | **0.3532** | perm mean `0.4889` (`p = 0.948`) | **1.000** | **NULL** |
| **Primary B:** 5-context within-bout caw-order shuffle (`order_18d`) | 239 recs, 153 recordists | **0.5805** (`0.519–0.641`) | 200-shuffle mean **`0.5872`** (`Δ = -0.0067`, `p = 0.622`) | **1.000** | **NULL** |

Sub-block breakdown on Primary A (`n = 88`): `cadence_10d` = `0.4642`, `order_18d` = `0.3363`, whereas `0113`'s `bag_47d` on the exact same 88 recordings = `0.6321`. On S4 (within-bout order shuffle on owl vs. hawk), `order_18d` scored `0.3363` vs. shuffled mean `0.4746` (`p = 0.970`, null).

### Secondary results

1. **S1 — Five-context comparison on the same 239 single-bird recordings:**

   | Feature set | Raw macro AUC (95% CI) | Crowd (`crowgpt_b4`) regressed out | `raptor` | `begging` | `roost` | `food` | `flight` |
   |---|---:|---:|---:|---:|---:|---:|---:|
   | `bout_syntax_28d` (channel-free) | **0.6490** (`0.583–0.705`) | **0.6389** (`0.575–0.695`) | 0.565 | 0.756 | 0.572 | 0.667 | 0.685 |
   | `cadence_10d` (burst/ICI only) | 0.5980 (`0.529–0.658`) | — | 0.513 | 0.762 | 0.524 | 0.506 | 0.685 |
   | `bag_47d` (`0113` features, same recs) | **0.6521** (`0.592–0.711`) | **0.6314** (`0.570–0.691`) | 0.673 | 0.758 | 0.398 | 0.667 | 0.765 |

   Notably, channel-free `bout_syntax_28d` matches `bag_47d` overall (`0.649` vs. `0.652`, and `0.639` vs. `0.631` after regressing out `crowgpt_b4` crowd score), driven by `begging` (`0.756`), `flight_contact` (`0.685`), and `food_foraging` (`0.667`) — **not** by sequential caw order (Primary B proved permuting caws inside every bout leaves `order_18d` unchanged at `0.587`), because within-bout step magnitudes (`|x_{t+1} - x_t|`) measure per-bout pitch/duration variability even when order is scrambled.

2. **S2 — Great Horned Owl vs. Barred Owl (`n = 46` single-bird strict recordings: 33 GHO, 13 Barred, 36 recordists):**
   - `bout_syntax_28d`: **`0.4755`** (`perm_p = 0.469`, **null**).
   - `bag_47d`: **`0.9394`** (`perm_p = 0.0025`).
   - *Exploratory post-hoc check on why `bag_47d` hit `0.939` while `bout_syntax_28d` was chance:* Longitude alone scores **`0.755` AUC** on these 46 files (Barred Owls in the corpus are Eastern woodland recordings while many Great Horned Owls are Western open-country recordings), MFCCs alone (`[15:41]`) score `0.921`, spectral/prosody means without MFCCs (`[0:15, 41:47]`) score `0.916`, and restricting to Eastern US (`lng > -95`) leaves only `n = 5` Barred Owls (`24 vs. 5`, `0.842`, `perm_p = 0.020` — too few to trust). So bout syntax carries zero GHO-vs-Barred signal, and `bag_47d`'s gap lives in static spectral/channel timbre plus range geography rather than phrase delivery.

3. **S3 — Early (`0–15 s`) vs. sustained (`> 15 s`) single-bird bouts within the same raptor-mobbing recording (`n = 70` paired recordings):**
   - Median intra-bout ICI: `0.538 s` early vs. `0.542 s` sustained (Wilcoxon `p = 0.166`, null).
   - Median caw duration: `0.242 s` early vs. `0.245 s` sustained (`p = 0.313`, null).
   - Median F0: `1421 Hz` early vs. `1405 Hz` sustained (`p = 0.299`, null).
   - Archive recordings typically begin *after* the recordist hears an ongoing mob and hits record, so `0–15 s` of an archive file is rarely the biological onset of recruitment.

## Reading & what it changed

- **"Maybe owl vs. hawk lives in phrase cadence or sequential caw order rather than single caws" is answered: no.** On 88 strict single-bird recordings from 72 recordists, `bout_syntax_28d` (`0.353`) and `cadence_10d` (`0.464`) find nothing at all separating owl mobs from hawk mobs.
- **Sequential order of caws inside a single bird's bout carries zero context or predator information (`Δ = -0.007` against within-bout shuffles).** That directly answers the sequential-structure question in `FUTURE.txt` (`DO ALARM CALLS HAVE SEQUENTIAL STRUCTURE?`) for prosodic trajectories: whatever context signal single-bird calling carries (`0.64–0.65` macro AUC) comes from **per-bout summary statistics and call duration/pitch distributions**, not from the order in which caws are arranged inside a burst.
- **Saved `archive_window_splits.json` and `crowgpt_b4_cut.json`** under `data/experiments/0115-bout-syntax/` (`T = 0.652`, 90.0% one-crow precision) for reuse in Experiment `0118`.
