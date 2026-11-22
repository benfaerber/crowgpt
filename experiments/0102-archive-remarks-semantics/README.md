# 0102 — Can archive free-text remarks yield witnessed semantic labels, and do owl vs. hawk mobbing calls separate acoustically?

**Question.** Mapping crow calls to meaning has been bottlenecked by witnessed context — 8.1 minutes of field-labeled audio so far. Before building new collection pipelines, how much witnessed semantic-context audio is *already* sitting inside Xeno-canto (`rmk`) and Macaulay Library (`mediaNotes`) free-text remarks in `data/corvid.db`? And on strictly recordist-grouped cross-validation — after stripping every clip/window where BirdNET hears a raptor or owl itself — do those witnessed semantic contexts separate acoustically?

**Method.**
1. Screened all 23,948 downloaded Xeno-canto + Macaulay recordings in `data/corvid.db` (2,645 American Crow with non-empty remarks) with a broad semantic keyword pass, yielding 971 American Crow candidates and 211 predator-context candidates across 6 other *Corvus* species (1,182 total).
2. Classified all 1,182 remarks with an LLM into a 13-class semantic schema (`labels.json`), enforcing `witnessed=true` only when the recordist explicitly observed the trigger or behavior (filtering out *"dead tree"*, *"unseen predator"*, *"originally thought mobbing"*, and passive background-species mentions) and flagging `pred_vocal=true` whenever a predator was described as calling or listed in Xeno-canto's `also`.
3. Extracted per-3s-window BirdNET detections (`min_conf=0.05`), 1024-d BirdNET embeddings pooled via `mean+std+max` (`pipelines/training/pooling.py`), and 41 interpretable crow-band (600–4500 Hz) prosodic/spectral features via `run.py` (CPU-only).
4. Evaluated with 5-fold `StratifiedGroupKFold` grouped strictly by recordist (`recordist` / `group_key`), alongside a metadata-only null baseline (`duration_s`, time-of-day sin/cos, `lat`, `lng`, `source`), a 200-shuffle permutation test, and strict predator-audio masking (`pred_vocal=false` AND zero BirdNET raptor/owl detection >= 0.05 anywhere in the recording).

## Yield — witnessed American Crow audio already on disk

| Context | Witnessed clips | Unique recordists | Crow-detected (`>=0.25`) | BirdNET raptor `>=0.05` | Audio (min) |
|---|---:|---:|---:|---:|---:|
| `hawk_mobbing` | 132 | 91 | 130 | 61 | 154.9 |
| `owl_mobbing` | 120 | 90 | 120 | 41 | 166.7 |
| `begging` | 77 | 60 | 67 | 26 | 451.1 |
| `roost_gathering` | 51 | 36 | 50 | 28 | 88.6 |
| `territorial_agonistic` | 50 | 35 | 42 | 12 | 37.3 |
| `rattle_social` | 48 | 41 | 35 | 21 | 69.6 |
| `food_foraging` | 39 | 33 | 36 | 19 | 44.5 |
| `flight_contact` | 15 | 12 | 14 | 6 | 17.4 |
| `human_disturbance` | 14 | 12 | 12 | 3 | 34.8 |
| `mammal_scold` | 9 | 9 | 9 | 3 | 8.6 |
| `unidentified_mobbing` (witnessed act) | 5 | 5 | 5 | 3 | 6.1 |
| `dead_crow` | 1 | 1 | 1 | 1 | 1.4 |
| **Total** | **561** | — | **521** | — | **1,081.1 (18.0 hr)** |

Top witnessed predator triggers (American Crow):
- **Owls:** Great Horned Owl (84), Barred Owl (28), unspecified owl (6), Spotted Owl (1), Long-eared Owl (1).
- **Hawks/diurnal raptors:** Red-tailed Hawk (58), Cooper's Hawk (19), Red-shouldered Hawk (16), unspecified hawk (9), Bald Eagle (6), Northern Goshawk (4), Broad-winged Hawk (2).
- **Timestamped gold nuggets:** 25 witnessed American Crow remarks include explicit timestamps (e.g. `0:17` begging onset).
- Across all 7 *Corvus* species: 193 witnessed `hawk_mobbing`, 130 `owl_mobbing`, and 37 `mammal_scold` (14 fox, 9 cat, 8 dog, 4 raccoon).

## Results

### 1. Seven-class American Crow semantic separability (recordist-grouped 5-fold, `n=476`)

| Feature set | Bal. Acc | Macro F1 | Macro AUC | `begging` | `roost` | `owl` | `agonistic` | `rattle` | `hawk` | `foraging` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BirdNET clean crow windows (3072d) | 0.474 | 0.478 | **0.811** | **0.963** | **0.933** | **0.835** | **0.790** | **0.741** | **0.721** | **0.694** |
| BirdNET full clip (3072d) | 0.495 | 0.501 | 0.840 | 0.964 | 0.935 | 0.854 | 0.798 | 0.836 | 0.756 | 0.737 |
| Pure prosody + MFCC (41d, no BirdNET) | 0.382 | 0.362 | **0.746** | 0.842 | 0.864 | 0.773 | 0.711 | 0.707 | 0.688 | 0.637 |
| Metadata-only null (dur, time, lat/lng, src) | 0.178 | 0.151 | 0.528 | 0.521 | 0.476 | 0.496 | 0.620 | 0.504 | 0.579 | 0.496 |

### 2. Referential predator alarm: American Crow `owl_mobbing` vs. `hawk_mobbing`

| Subset / Feature set | n (owl / hawk) | Recordists | ROC-AUC | Bal. Acc |
|---|---:|---:|---:|---:|
| All crow windows (raw) | 250 (120 / 130) | 166 | 0.768 | 0.709 |
| **Strict zero-raptor audio** (`pred_vocal=F`, BirdNET raptor `<0.05` everywhere), pooled 3072d | 144 (78 / 66) | 114 | **0.769** (`p=0.005`*) | **0.737** |
| Strict zero-raptor, BirdNET mean-only (1024d) | 144 (78 / 66) | 114 | **0.778** | 0.730 |
| Strict zero-raptor, **Macaulay-only** | 139 (75 / 64) | 110 | **0.807** | 0.723 |
| Strict zero-raptor, **Eastern US only (`lng > -95`)** | 90 (47 / 43) | 73 | **0.750** | 0.664 |
| Strict zero-raptor, **within intense alarms only** (shipped `p(alarm) >= 0.5`) | 83 (55 / 28) | — | **0.711** | — |
| Strict zero-raptor, **pure prosody (41d)** | 144 (78 / 66) | 114 | **0.675** | 0.639 |
| Strict zero-raptor, **spectral + MFCC only** (no duration, `crow_frac`, or RMS) | 144 (78 / 66) | 114 | **0.663** | 0.613 |
| Strict zero-raptor, **metadata-only null** | 144 (78 / 66) | 114 | 0.469 | 0.448 |

*\*200-shuffle permutation test: `perm_mean = 0.501`, `perm_max = 0.655`, `p = 0.005` (0/200 shuffles reached 0.769).*

**What actually differs acoustically?**
1. **Intensity & persistence:** The shipped American Crow call-type head scores strict `owl_mobbing` at median `p(alarm call) = 0.984` vs. `0.308` for `hawk_mobbing` (AUC `0.690` from that single probability). On pure prosody, owl mobbing has higher crow coverage (`crow_frac` 0.955 vs. 0.809, `p = 5.6e-4`), higher duty cycle (0.377 vs. 0.316, `p = 0.007`), and lower spectral/amplitude variance (`flatness_std` 0.037 vs. 0.052, `p = 5.9e-4`; `centroid_hz_std` 278 vs. 363 Hz, `p = 0.0013`), while hawk mobbing is burstier with faster sharp onsets (`onset_rate_hz` 1.72 vs. 1.38/s, `p = 0.017`).
2. **Calling speed (crow-band 700–4500 Hz envelope peak-rate & modulation tempo):** Owls are called at significantly faster sustained rates than hawks (**2.67** vs. **2.00 caws/s**, `p = 0.016`), and within owls Great Horned Owls are significantly faster than Barred Owls (**2.83** vs. **2.33 caws/s**, `fast 3.2–7 Hz` AUC **0.738**, `p = 0.0034`). Archive `human_disturbance` clips (`n=12`) are slower still (**1.33 caws/s**, even in mobs of 10–35 birds) and separate from strict `owl_mobbing` at **0.805 BirdNET / 0.718 prosody AUC** and from strict `hawk_mobbing` at **0.645 BirdNET / 0.766 prosody AUC** (metadata nulls 0.563 / 0.523).
3. **Survives speed-matching, density-matching, and full linear orthogonalization:**
   - **1-to-1 speed-matched** (`n=112`: 56 owl vs. 56 hawk, 89 recordists; `caws/s`, `p90`, and modulation centroid balanced `p > 0.13`, speed-only AUC `0.581`): BirdNET mean-only = **0.735 AUC** (`perm_p = 0.005`), pure timbre/spectral+MFCC (no speed, duration, RMS, or BirdNET) = **0.711 AUC** (`perm_p = 0.005`).
   - **1-to-1 matched on speed + `crow_frac` + `duty_cycle` + `p(alarm)`** (`n=100`: 50 vs. 50, 84 recordists; matched-covariates AUC `0.597`): pure timbre/spectral+MFCC = **0.672 AUC** (`perm_p = 0.015`), BirdNET pooled = **0.667 AUC** (`perm_p = 0.010`), BirdNET mean-only = **0.661 AUC** (`perm_p = 0.010`).
   - **Full-sample in-fold orthogonalization** (`n=143`, linearly regressing all 8 speed/density/duration/`p(alarm)` covariates out of every feature inside each fold): BirdNET mean residual = **0.653 AUC**, BirdNET pooled residual = **0.648 AUC**, pure timbre residual = **0.616 AUC**.
4. **Not geography or sub-trigger artifact:** Within Eastern US clips only (`lng > -95`), BirdNET holds at **0.750 AUC**; within strongly alarming clips (`p(alarm) >= 0.5`, `n=83`), **0.711 AUC**. Within strict owl clips (`n=70`, 53 Great Horned Owl vs. 17 Barred Owl, 57 recordists), BirdNET reaches **0.787 AUC** and pure prosody **0.773 AUC** (longitude alone 0.369, metadata 0.600; median `p(alarm)` 0.984 vs. 0.899). Conversely, Red-tailed vs. Cooper's/Red-shouldered Hawk is null (**0.405 AUC**, `n=40`).

### 3. Calibrated 4-class Threat Translator head & zero-shot Poe Family field check (`train_threat_head.py`)

Trained a block-standardized One-vs-Rest logistic head with out-of-fold Platt sigmoid calibration on 365 strict witnessed American Crow archive recordings across 228 recordists (`owl=78`, `hawk=66`, `terrestrial=21` [12 `human_disturbance` + 9 `mammal_scold`], `non_threat=200`).

| Arm (5-fold recordist-grouped CV) | Macro AUC | `sat > 0.99` | `owl` | `hawk` | `terrestrial` | `non_threat` | `owl vs hawk` | `owl vs ter` | `hawk vs ter` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BirdNET mean-only (1024d) | 0.765 | 0.6% | 0.874 | 0.717 | 0.622 | 0.847 | 0.783 | 0.697 | 0.665 |
| BirdNET pooled-only (3072d) | 0.775 | 0.5% | 0.879 | 0.716 | 0.667 | 0.837 | 0.789 | 0.778 | 0.693 |
| BirdNET mean + prosody + speed (`w=0.35`) | 0.771 | 0.5% | 0.879 | 0.737 | 0.626 | 0.842 | 0.798 | 0.687 | 0.687 |
| **BirdNET pooled + prosody + speed (`w=0.35`)** | **0.786** | **0.7%** | **0.881** | **0.730** | **0.690** | **0.844** | **0.797** | **0.752** | **0.714** |

Saved the winning calibrated head to `data/models/american-crow/threat_clf.joblib` (gitignored) and metrics to `threat_metrics.json`. Out-of-fold Platt calibration cut probability saturation (`>0.99`) from 32% on the shipped call-type head down to **0.7%**.

**Zero-shot validation on Ben's 29 kept Poe Family field captures (`fieldserver/instance/field.db`, `keep = 1`, 25 crow-detected, zero owls/hawks present):**
- **Zero owl false alarms (`0 / 25` with `P_owl >= 0.5`)** across all crow-detected backyard captures, even where the shipped call-type head saturated `p(alarm) = 1.00`.
- **`P(terrestrial)` separated Ben's witnessed stranger-alarm captures** (`#87`, `#88`, `#113`, `#154`, `#155`, `#156`, `#158`, `n=7`) **from his benign/feeding/fledgling captures** (`#69`, `#94`–`#97`, `#104`–`#105`, `#114`, `#116`, `n=9`) **at `0.810 AUC`** (median `0.051` vs. `0.022`; highest `P_ter = 0.10` on `#154`, `stranger_passing`).
- **`P(owl)` on the same Stranger vs. Benign split was `0.508` (chance)** and `P(hawk)` was `0.222` — confirming `P(terrestrial)` is responding specifically to terrestrial/human alarm calls rather than generic loudness.
- *Calibration note:* Because `terrestrial` is 5.8% of the training set (21/365), Platt-calibrated raw `P(terrestrial)` reflects that base rate (0.05–0.10 on positives vs. 0.02 on negatives). Downstream thresholding should use class likelihood ratios (`P(c) / prior(c)`) or balanced-prior calibration once more terrestrial examples are added.

### 4. Confounded null: All-Corvus aerial predator vs. mammal scold

BirdNET scored **0.869 AUC** (`n=197`, 24 mammal vs. 173 owl/hawk), **but metadata alone scored 0.799 AUC** because mammal scolds in the archives come predominantly from European Hooded and Carrion Crows while owl/hawk clips are mostly North American American Crows. Treat cross-species aerial-vs-mammal as confounded until within-species mammal counts grow (currently only 9 American Crow).

## Caveats

- **Perched vs. aerial ecology remains entangled with predator identity.** Owls are usually mobbed while perched in cover by a dense stationary chorus, whereas hawks are often mobbed in flight or brief flybys. That ecological difference likely explains part of the intensity/persistence gap (`p(alarm)` 0.984 vs. 0.308), though the within-alarm separation (0.711), spectral-only prosody (0.663), and GHO-vs-Barred split (0.773 prosody AUC, both perched owls) suggest threat level or predator-specific vocal modulation beyond mere perched/flying geometry.
- **BirdNET hears background habitat.** Full-clip embeddings (0.840 macro AUC) edge out clean crow-only windows (0.811), confirming that background soundscape adds a small boost when unmasked. Always report crow-only masked windows and compare against prosody + metadata nulls.
- **Macaulay dominates the strict subset** (`n=139` of 144) because Xeno-canto has far fewer American Crow remarks with witnessed predator triggers.

## What it changed

- **Replaced the assumption that archive data can't feed Problem 2 (semantics).** Free-text remarks already in `data/corvid.db` yielded **561 witnessed American Crow recordings (~18 hours)** across 10+ semantic contexts with zero fieldwork and zero crowdsourcing — 133× the current field-labeled audio volume.
- **Established the first non-null, confounder-controlled semantic benchmark in the project:** 7-class witnessed semantic separation at **0.811 macro AUC** and strict zero-raptor owl-vs-hawk separation at **0.769 AUC** (`p = 0.005`, metadata null 0.469).
- **Flagged begging as recoverable from archive remarks:** 77 witnessed American Crow begging clips (67 crow-detected, 451.1 min total, **0.963 OvR AUC**) are immediately usable to bolster the weak begging class without waiting on seasonal fledglings.
- **Built and validated the first calibrated threat-translation head (`train_threat_head.py` -> `data/models/american-crow/threat_clf.joblib`):** BirdNET pooled + prosody + speed reached **0.786 macro AUC** (`owl` 0.881, `owl vs hawk` 0.797, `sat > 0.99` = 0.7%), achieved **0/25 owl false alarms** on Ben's kept backyard Poe Family captures, and separated witnessed stranger-alarm captures from benign/feeding/fledgling captures zero-shot at **0.810 AUC** on `P(terrestrial)`.
- **Added `labels.json`** (portable Xeno-canto + Macaulay semantic labels), `threat_metrics.json`, and `crowgpt.progress.Run`-instrumented scripts so future embedders (CrowGPT hidden states, Perch, HuBERT) can be benchmarked directly on the same 561 witnessed semantic recordings.
