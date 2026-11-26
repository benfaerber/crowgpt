# 0121 — Pre-ship validation: unified `"none"` + uniform-pooling retrain, `"call" -> "rattle"`, and high-threshold raptor co-detections

**2026-11-23** · CPU · **answer: split verdict that justifies validating before shipping — (1) Uniform `1024-d` window-mean pooling + pure `crow-tools` `"rattle"` (`C = 0.1`) is a clear win (`0.845` grouped CV macro-F1, `0.967` rattle AUC, and lifts `★kept` multi-window accuracy from `50%` [7/14] to `100%` [14/14], overall `84% -> 90%`); (2) archive `garbage.npz` `"none"` FAILS field validation — BirdNET (`hp300`, `>= 0.25`) already blocks `82.9%` of `crowCount == 0` upstream, and on the `98` windows that fool BirdNET, `"none"` catches only `17–23%` while falsely abstaining on `20–26%` of Ben's real `★kept` phone calls; (3) raptor co-detections need true taxonomic filtering (excluding `Common Nighthawk`!) at `conf >= 0.70` (`0/29` false alarms on kept captures, `1.9%` on non-raptor archive clips)**

> **Pre-registration (`52b3ade`, revised in `4e4fdbe` per Ben's 5 design corrections before running).**

## The three questions validated

Following Ben's review, `crowd` (`0109`) and `calling_density` (`0107`) were dropped, and `song` was left unsplit (`0012`: `song` is already `softSong`, and `call` in `crow-tools` is `rattle`). Before touching `analyzer/`, we ran four concrete checks (`run.py` + `audit.py`):

1. **Upstream BirdNET gate + `"none"` class:** How many of `0036`'s `572` `crowCount == 0` segments (`garbage.npz`) actually get past `analyzer/birdnet.py`'s `hp300` BirdNET corvid check (`>= 0.10` / `>= 0.25`), how many of *those* leaked windows does a retrained `"none"` class catch in recording-grouped CV, and what does `"none"` do to Ben's `★kept` phone captures?
2. **Uniform `1024-d` window-mean pooling + `"call" -> "rattle"`:** Does replacing `3072-d` `[mean, std, max]` (`std = 0` on `crow-tools`, `std > 0` on `archive`) with uniform `1024-d` `M.mean(0)` across every row — and training `"rattle"` purely on `crow-tools` `rattle` rather than mixing in weak archive `"call"` clips — fix multi-window regions on field audio without hurting grouped CV?
3. **High-threshold calibration for `"BirdNET also heard: <Raptor> (<conf>)"`:** Across `0.25`, `0.50`, `0.70`, `0.80` on `0102`'s `561` witnessed archive clips and Ben's `29` `★kept` captures, where do false alarms and non-raptor name collisions sit?

---

## Results

### 1. Upstream BirdNET corvid gate & why archive `"none"` fails field validation

Running `analyzer/birdnet.py`'s exact `hp300` (4th-order 300 Hz high-pass) + BirdNET `2.4` detector over all `572` embedded `crowCount == 0` segments (`garbage.npz`):

| Stage on `572` `crowCount == 0` segments | Count | Share of `572` | What happens |
|---|---:|---:|---|
| Blocked upstream by BirdNET (`corvid < 0.10`) | **450** | **78.67%** | Never reaches `SpeciesHead` at all (top detections: warblers, grosbeaks, gulls, robins, sparrows) |
| Blocked from confident output (`corvid < 0.25`) | **474** | **82.87%** | Never reaches confident `analyzer/` output (`24` sit in `0.10–0.25` inert candidates) |
| **Leaks past `CROW_MIN_CONF >= 0.25`** | **98** | **17.13%** | **The actual false-positive pool `SpeciesHead` faces on confident regions** |

Now compare what adding `"none"` (`crowCount == 0`) does on **strict 5-fold recording-grouped CV** (shared `file_id`s never split across train/test) and on **Ben's `★kept` field captures** (`50` unambiguous `alarm call` [39] + `begging` [11] human labels):

| Head variant (`C = 0.1` on `1024-d`, vs. `3072-d` baseline) | All `572` garbage rejected | **Leaked `98` (`corvid >= 0.25`) rejected** | `crow-tools` call false-abstain | `crow-tools` CORE4 macro-F1 (uncond / cond) | `★Kept` (`n = 50` alarm+beg) false-abstain | `★Kept` (`n = 50`) unconditional accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `M0` (`3072-d`, legacy mix, no `none`) | `0.0%` (`80.8%` `p > 0.5`) | `0.0%` (`96.9%` `p > 0.5`) | `0.0%` | **0.8479** / 0.8479 | `0 / 50` (`0%`) | `84.0%` (`42/50`) |
| **`Uniform 1024-d` + pure `rattle`, NO `none`** (`audit.py`) | `0.0%` | `0.0%` | **`0.0%`** | **0.8450** / 0.8450 | **`0 / 50` (`0%`)** | **`90.0%` (`45/50`)** |
| `M2c` (`1024-d` + balanced `none` class) | `68.5%` | **`23.5%`** (`23/98`) | `6.7%` | `0.8329` / `0.8616` | **`13 / 50` (`26%`)** (`15/58` all) | `62.0%` (`53.5%` all 58) |
| `Unweighted none` (`1024-d`, `class_weight=None` on `none`) | `65.4%` | **`17.4%`** (`17/98`) | `5.2%` | `0.8376` / `0.8587` | **`10 / 50` (`20%`)** (`11/58` all) | `70.0%` (`35/50`) |
| `Garbage as negatives + p < 0.35 floor` (`1024-d`) | `60.3%` | **`14.3%`** (`14/98`) | `7.4%` | `0.8373` / `0.8680` | **`9 / 50` (`18%`)** | `70.0%` (`35/50`) |
| `M3` (`1024-d` 6-class softmax with `none`) | `62.9%` | **`23.5%`** (`23/98`) | `7.3%` | `0.7994` / `0.8304` *(kills co-occurrence: `0/228`)* | **`14 / 50` (`28%`)** | `53.5%` (all 58) |

**Why `"none"` failed so starkly once tested properly:**
1. **`0036`'s `70.6%` rejection was mostly redundant with BirdNET's own species gate:** `79%` of `garbage.npz` has `corvid < 0.10`. On the `98` windows where BirdNET's `1024-d` penultimate layer *already* hallucinated a crow (`>= 0.25`), a linear `"none"` probe on that **exact same `1024-d` vector** gets fooled `76.5%–85.7%` of the time too (`14–23%` rejected).
2. **Severe domain mismatch on real phone captures:** Archive `garbage.npz` consists of quiet ambient archive windows; distant crows on a phone mic (`30 m` away on the apartment roofline, e.g. Capture `103`) project closer to archive background than parabolic-dish Xeno-canto calls do, causing `"none"` to wipe out **`20%–26%` of real `★kept` calls** (even without `hp300`, `10–12` of `50` raw kept spans are falsely abstained).

---

### 2. Uniform `1024-d` window-mean pooling + `"call" -> "rattle"` (without `"none"`) is a decisive upgrade

Comparing legacy `3072-d` (`[mean, std, max]`, archive `"call"` mixed into `rattle`) against **Uniform `1024-d` (`M.mean(0)`) + pure `crow-tools` `"rattle"` (`C = 0.1`, no `"none"`)**:

| Metric | Shipped / `M0` (`3072-d`, legacy `"call"` mix) | `M1` (`1024-d`, legacy `"call"` mix) | **Recommended Retrain: Uniform `1024-d` + Pure `rattle` (`C = 0.1`, no `none`)** |
|---|---:|---:|---:|
| `crow-tools` single-label CORE4 macro-F1 | **0.8479** | 0.8001 (`C=1.0`) | **0.8450** |
| `alarm call` grouped AUC | 0.9428 | 0.9037 | **0.9267** |
| `begging` grouped AUC | 0.9272 | 0.9207 | **0.9272** |
| **`rattle` grouped AUC (`AP` w/ garbage)** | 0.9545 (`0.865`) *(polluted on multi-win!)* | 0.8763 (`0.638`) | **0.9669 (`0.8772`)** |
| `song` (`softSong`) grouped AUC | 0.9033 | 0.8879 | **0.9034** |
| `flight call` grouped AUC (within-archive AUC) | 0.9452 † (`0.7485`) | 0.8528 (`0.7413`) | **0.8594 (`0.7400`)** |
| **`★Kept` `alarm`+`begging` `X_span` (`n = 50`)** | `84.0%` (`42/50`) | — | **`90.0%` (`45/50`)** |
| **`★Kept` multi-window (`>= 6 s`) `alarm`+`begging` (`n = 14`)** | **`50.0%` (`7/14`)** | — | **`100.0%` (`14/14`)** |

*† `3072-d`'s `0.945–0.975` `flight call` AUC was the `std > 0` archive-corpus shortcut; within the archive clips alone, `3072-d` (`0.749`) and `1024-d` (`0.740`) are identical.*

**Concrete fixes observed on Ben's `29` `★kept` captures:**
- **Eliminates the multi-window `std > 0` bug:** On the `14` multi-window (`>= 6 s`) `alarm call` and `begging` labels on `★kept` captures, the shipped `3072-d` head got **half wrong (`7/14`)** — calling Capture `100` (`48–60 s`, `66–78 s`) and Capture `113` (`30–36 s`) `"call"` (`p = 0.95–1.00`) and calling Capture `116` (`12–21 s`, begging young!) **`"flight call"` (`p = 0.78`)** solely because `std > 0` matched the 160 archive clips. Uniform `1024-d` gets **`14 / 14` (`100%`)** right (`Capture 116` -> `begging 0.75`; `Capture 100` & `113` -> `alarm call`).
- **Prevents false `"rattle"` flood when renaming `"call"` -> `"rattle"`:** Had we renamed `"call"` -> `"rattle"` on the shipped `3072-d` head without retraining on uniform `1024-d` + pure `crow-tools` `rattle`, `17 of 54` confident regions on the Poe Family captures (ordinary multi-window caws and alarms) would have been displayed as **`"rattle"` (`p = 0.95–1.00`)**. Excluding weak archive `"call"` clips from the `rattle` binary head lifts `rattle` AUC from `0.876` to **`0.967`** and stops ordinary multi-window caws from firing `rattle` (`0 / 8` false rattles on Ben's kept contact caws).

---

### 3. Raptor co-detection threshold calibration & the `"Common Nighthawk"` bug

| BirdNET threshold | `0102` stated vocal raptor recall (`n = 19`) | `0102` non-raptor crow scenes firing (`n = 429`) | Ben's `29` `★kept` captures firing (raw `_is_raptor`) | Ben's `29` `★kept` captures firing (**true raptors only**) |
|---|---:|---:|---:|---:|
| `conf >= 0.25` | `47.4%` (`9/19`) | `7.23%` (`31/429`) | `2 / 29` (`#69 Common Nighthawk 0.72`, `#116 Cooper's Hawk 0.29`) | `1 / 29` (`#116 Cooper's Hawk 0.29` — false alarm) |
| `conf >= 0.50` | `42.1%` (`8/19`) | `3.73%` (`16/429`) | `1 / 29` (`#69 Common Nighthawk 0.72`) | **`0 / 29` (`0.0%`)** |
| **`conf >= 0.70`** | **`36.8%` (`7/19`)** | **`1.86%` (`8/429`)** | `1 / 29` (`#69 Common Nighthawk 0.72`) | **`0 / 29` (`0.0%`)** |
| `conf >= 0.80` | `36.8%` (`7/19`) | `1.40%` (`6/429`) | `0 / 29` | **`0 / 29` (`0.0%`)** |

- **Taxonomic bug caught:** `0102`'s substring helper matched `"hawk"` inside **`Common Nighthawk` (*Chordeiles minor*, `0.72` on Capture `69`)** — a nightjar (*Caprimulgidae*) whose nasal *peent* resembles a crow/fledgling call. Matching raptors strictly by scientific family/genus (*Accipitridae*, *Falconidae*, *Strigidae*, *Tytonidae*, *Cathartidae* — or excluding `chordeiles` / `nighthawk`) eliminates Capture `69` immediately.
- **Recommended threshold:** **`conf >= 0.70`** (`1.86%` non-raptor archive rate, `0/29` on kept captures, `36.8%` recall on stated vocal raptors, resistant to weak jay mimicry), surfaced strictly as `co_detections: [{"species": "Cooper's Hawk", "scientific_name": "Astur cooperii", "confidence": 0.74}]` -> UI string `"BirdNET also heard: Cooper's Hawk (0.74)"`.

---

## What it changed

1. **Retrained `pipelines/training/models/american-crow/{calltype_clf.joblib, metrics.json}` (`make train-crow` -> `pipelines/training/train_head.py --backbone birdnet --head onevsrest --source window-mean --write`):**
   - Added `birdnet_window_mean` (`1024-d` `M.mean(0)`) alongside `birdnet_pooled_mean_std_max` (`3072-d`) in `pipelines/training/pooling.py` and `analyzer/birdnet.py` so the 5 archive-only corvid heads keep loading while American Crow runs on uniform `1024-d` (`C = 0.1`, pure `crow-tools` `rattle`).
   - Kept archive `garbage.npz` `"none"` **out** of the shipped head (`82.9%` of `crowCount == 0` is already blocked by BirdNET `>= 0.25` upstream, and archive `"none"` falsely abstained on `20–26%` of real phone calls). Defer `"none"` until genuine phone field negatives exist.
2. **Emitted `"rattle"` instead of `"call"` on American Crow:** `SEED_LABELS` already maps `("rattle", "call")`, and `promo/src/scan-timeline.ts` now colours `rattle` with the same `#6ea8fe` swatch.
3. **Kept true taxonomic raptor co-detections at `RAPTOR_MIN_CONF = 0.70`:** `analyzer/birdnet.py` (`raptor_name` + `analyze_with_co_detections`), revision `0045_analysis_co_detections` on `analysis_results`, `dashboard/src/components/DetectedCalls.tsx`, and `promo/src/scan-timeline.ts` report them strictly as `"BirdNET also heard: <Species> (<conf>)"` while rejecting nightjars (`Common Nighthawk` *Chordeiles minor*) and substring look-alikes.
4. **Left BirdMixIT (`0120`), `crowd` (`0109`), and `calling_density` (`0107`) out of `analyzer/`.**
