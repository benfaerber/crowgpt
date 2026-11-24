# 0121 — Pre-ship validation: unified `"none"` + uniform-pooling retrain, `"call" -> "rattle"`, and high-threshold raptor co-detections

**2026-11-23** · CPU · **status: revised pre-registration (incorporating Ben's 5 design corrections before running)**

> **Scope corrected before execution:** Dropped `crowd` (`0109`: research covariate only) and `calling_density` (`0107`: tracks crowd size, roosts match mobs). Dropped `song` splitting (`0012`: `song` is already `softSong`, and `call` is `rattle`). Focused strictly on validating the three real `analyzer/` changes:
> 1. **One retrain** adding an explicit `"none"` class (`crowCount == 0`) **and** applying **one uniform pooling scheme (`1024-d` window mean)** across every training row and every `analyzer/` region, measured on `crowCount == 0` windows that **actually pass BirdNET's upstream corvid check** (`>= 0.10` / `>= 0.25` after `hp300`).
> 2. **Relabelling `"call"` -> `"rattle"`** (`0012`), including checking whether weak archive `"call"` clips in `pooled_embeddings.npz` dilute `crow-tools`'s `rattle` positives.
> 3. **Threshold calibration for `"BirdNET also heard: <Raptor> (<conf>)"`** (`0.25`, `0.50`, `0.70`, `0.80`), checking jay-mimicry co-occurrence, `0102`/`0116` `pred_vocal` alignment, and all `29` `★kept` field captures.

---

## Pre-declared protocol

### 1. Measuring the true upstream `crowCount == 0` false-trigger rate through `analyzer/`'s BirdNET gate

`0036` scored all `572` `crowCount == 0` segments (`garbage.npz`) directly with the call-type head (`97.0%` assigned a call at `p > 0.5`), noting this is an upper bound because `analyzer/birdnet.py` only hands `SpeciesHead` windows where BirdNET (`hp300` 300 Hz high-pass) already detected a corvid (`>= 0.10` candidate, `>= 0.25` confident).

We run `analyzer/birdnet.py`'s exact `hp300` + BirdNET `2.4` pass over all `578` `crowCount == 0` segments with audio on disk to measure:
1. **Upstream BirdNET leak rate:** Fraction of `crowCount == 0` segments where BirdNET detects a corvid at `>= 0.10` (candidate) and at `>= 0.25` (confident).
2. **Downstream head rejection rate (strictly 5-fold recording-grouped CV, shared `file_id`s never split across train/test):** Fraction of `crowCount == 0` segments rejected both across **all `572` garbage segments** (`0036` comparison) and specifically across the **BirdNET-leaked subset (`corvid >= 0.10` and `>= 0.25`)** — the exact false triggers `SpeciesHead` actually faces in production.

### 2. One retrain: `"none"` class + uniform `1024-d` window-mean pooling

In the shipped `3072-d` training cache (`INGEST_POOLED + ARCHIVE_POOLED`), `crow-tools` rows are single 3 s windows (`std = 0`, `max = mean`) while `archive` rows (including all `40` `flight call` clips) are multi-window clip pools (`std > 0`). Thus long regions at inference (`std > 0`) were out-of-distribution relative to `crow-tools`, while `flight call` leaned on `std > 0` as a corpus shortcut.

Using `M.mean(0)` (`1024-d`, the mean of BirdNET 3 s window vectors) puts 1-window (`3 s`) and multi-window (`6 s+`) training rows and `analyzer/` regions in **one identical feature space**. Under 5-fold recording-grouped CV (`crowtools_keyed [2,338] + archive [160] + garbage [572]`), we compare:
- **`M0_3072_no_none`:** Legacy inconsistent `3072-d` `[mean, std, max]`, 5 classes, no `"none"`.
- **`M1_1024_no_none`:** Uniform `1024-d` window-mean, 5 classes, no `"none"` (isolating the pooling change alone, including honest `flight call` AUC once the `std > 0` shortcut is gone).
- **`M2_1024_ovr_with_none` (Primary candidate):** Uniform `1024-d` `MultiLabelHead(alarm call, begging, rattle, song, flight call, none)` trained with `garbage` as `Y = {"none"}` (preserving multi-label co-occurrence like `begging + rattle` while abstaining when `"none"` wins or `P("none") >= 0.50` or `max(P_call) < 0.50`).
- **`M3_1024_softmax_with_none`:** Single-label 6-class softmax (`alarm call, begging, rattle, song, flight call, none`) reported alongside to compare calibration on `"none"` vs. loss of co-occurrence.

### 3. `"call" -> "rattle"` purity check (`0012` follow-up)

In `crow-tools`, `FLAG_TO_CORE` maps `"rattle" -> "call"` (`511` positives) and `"softSong" -> "song"`, whereas `recover_and_pool.py` mapped weak archive `"call"` / `"caw"` / `"contact call"` tags into `"call"` (`~80` archive rows). Now that the class will be displayed honestly as **`"rattle"`**, we compare:
- Training `"rattle"` on `crow-tools` `rattle` + archive `"call"` (legacy mix) vs. training `"rattle"` **purely on `crow-tools` `rattle`** (leaving archive clips without `"rattle"` unassumed on the `rattle` binary head while keeping archive clips for `flight call`, `alarm call`, `song`, `begging`), scored on `crow-tools` `rattle` grouped CV + Ben's `field.db` human labels.

### 4. High-threshold calibration for `"BirdNET also heard: <Raptor> (<conf>)"`

Across confidence thresholds **`0.25`, `0.50`, `0.70`, `0.80`**, measure:
1. **`0102` witnessed American Crow archive set (`561` recordings):** Recall on remarks where the observer explicitly noted a vocal raptor (`pred_vocal == True`) vs. firing rate on remarks with `pred_vocal == False`, split by whether BirdNET **also detected a jay** (`Blue Jay`, `Steller's Jay`, `Scrub-Jay`) in the same recording (quantifying jay mimicry).
2. **All `29` `★kept` field captures (`hp300` + Utah GPS filter, matching `analyzer/birdnet.py`):** Exact list of raptor detections surviving at each threshold, plus region-level replay of `M0_shipped` vs. `M2_1024_ovr_with_none` (`"call"` shown as `"rattle"`).
