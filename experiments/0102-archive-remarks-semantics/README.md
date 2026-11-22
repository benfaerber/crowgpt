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

Trained a block-standardized One-vs-Rest logistic head with out-of-fold Platt sigmoid calibration on **378** strict witnessed American Crow archive recordings across **234** recordists (`owl=79`, `hawk=67`, `terrestrial=26` [17 `human_disturbance` + 9 `mammal_scold`], `non_threat=206`; updated from an earlier 365-clip pass-1 run that had scored `0.786` macro AUC).

| Arm (5-fold recordist-grouped CV, `n=378`) | Macro AUC | `sat > 0.99` | `owl` | `hawk` | `terrestrial` | `non_threat` | `owl vs hawk` | `owl vs ter` | `hawk vs ter` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BirdNET mean-only (1024d) | 0.744 | 0.3% | 0.863 | 0.670 | 0.600 | 0.843 | 0.763 | 0.664 | 0.625 |
| BirdNET pooled-only (3072d) | 0.750 | 0.1% | 0.857 | 0.668 | 0.648 | 0.828 | 0.774 | 0.680 | 0.621 |
| BirdNET mean + prosody + speed (`w=0.35`) | 0.750 | 0.3% | 0.861 | 0.680 | 0.620 | 0.838 | 0.766 | 0.650 | 0.658 |
| **BirdNET pooled + prosody + speed (`w=0.35`)** | **0.757** | **0.2%** | **0.859** | **0.685** | **0.653** | **0.831** | **0.775** | **0.663** | **0.664** |

**Held-out operating-point precision & recall under the `lift >= 1.5` & `P(non_threat) < 0.70` verdict rule (378-clip OOF, `n=378`):**

| Class | True count | Predicted | True positives | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| `owl` | 79 | 90 | 51 | **0.567** | 0.646 |
| `hawk` | 67 | 51 | 20 | **0.392** | 0.299 |
| `terrestrial` | 26 | 21 | 2 | **0.095** | 0.077 |
| `non_threat` | 206 | 216 | 167 | **0.773** | 0.811 |

High ranking AUC did **not** translate to usable verdict-level precision: terrestrial verdicts were wrong 90% of the time (`2/21`) and hawk verdicts were wrong 61% of the time (`20/51`).

**Zero-shot check on Ben's 29 kept Poe Family field captures (`fieldserver/instance/field.db`, `keep = 1`, 25 crow-detected, zero owls or hawks present) — NULL / UNDERPOWERED:**
- **Hand-picked split (`n = 7` stranger alarms vs. `n = 9` benign/feeding/fledgling captures):** The stranger (`#87`, `#88`, `#113`, `#154`, `#155`, `#156`, `#158`) and benign (`#69`, `#94`–`#97`, `#104`–`#105`, `#114`, `#116`) ID lists were hand-picked by capture notes. On the 378-clip head, `P(terrestrial)` scored **`0.683` AUC** (median `0.049` vs. `0.030`, Mann-Whitney two-sided **`p = 0.243`**, one-sided `p = 0.122` — **not statistically significant**; the earlier `0.810` figure was from the smaller 365-clip head).
- **Verdict-rule false alarms & misses:** While `0/25` crow-detected captures had an owl false alarm (`P_owl >= 0.5` or owl verdict), the verdict rule flagged **`7/29` kept captures (`6/25` crow-detected: `#69`, `#89`, `#94`, `#105`, `#158`, `#178`, `#197`) as `"hawk"`** despite no hawk being present, and **`0/7` stranger-alarm captures reached a `"terrestrial"` verdict** (max `P_ter = 0.082`, below the `1.5×` prior threshold of `~0.103`).
- `P(owl)` on the same 7-vs-9 split was `0.532` (`p = 0.874`, null) and `P(hawk)` was `0.270` (`p = 0.142`, null).

**Perch 2.0 vs. BirdNET comparison (`benchmark_perch.py`, `perch_threat_metrics.json`, `n=378`):**
- On the 378-clip archive, Perch 2.0 pooled + prosody + speed reached `0.790` macro AUC (`owl` 0.844, `hawk` 0.697, `terrestrial` 0.781, `non_threat` 0.839) vs. BirdNET pooled + prosody + speed at `0.769` (`owl` 0.856, `hawk` 0.688, `terrestrial` 0.700, `non_threat` 0.830). With only 26 terrestrial clips, this difference is a **statistical tie** on the archive, and the 16 hand-picked Poe captures are far too small to rank the two backbones.

**Deployment decision:** Because of the weak held-out verdict precision (`20/51` hawk, `2/21` terrestrial), `7/29` backyard hawk false alarms, and a whole-recording vs. per-region train/serve mismatch, the prototype `analyzer/` integration (commit `7185300`) was reverted (`94d5e81`) pending caw-level and posture-controlled validation in Experiment `0103`.

### 4. Confounded null: All-Corvus aerial predator vs. mammal scold

BirdNET scored **0.869 AUC** (`n=197`, 24 mammal vs. 173 owl/hawk), **but metadata alone scored 0.799 AUC** because mammal scolds in the archives come predominantly from European Hooded and Carrion Crows while owl/hawk clips are mostly North American American Crows. Treat cross-species aerial-vs-mammal as confounded until within-species mammal counts grow (currently only 9 American Crow).

## Caveats

- **Recording-level, not call-level.** Every metric in 0102 is evaluated on whole-recording pooled embeddings and recording-level prosody/density summaries. It does **not** establish that an individual isolated crow caw differs between owl and hawk mobbing — see Experiment `0103`.
- **Non-crow bystander mobbers are NOT masked.** Only BirdNET raptor/owl windows (`>= 0.05`) were masked in 0102. Blue Jays, Steller's Jays, chickadees, and other woodland mobbers that frequently join owl mobs remain unmasked inside crow windows and may contribute to BirdNET's 0.769–0.778 separation.
- **Perched vs. aerial ecology remains entangled with predator identity.** Owls are usually mobbed while perched in cover by a dense stationary chorus, whereas hawks are often mobbed in flight or brief flybys. Posture was not coded in 0102; Experiment `0103` directly codes `perched` vs. `flying` from the archive remarks.
- **Whole-recording vs. per-region train/serve mismatch.** Training pooled whole recordings (`duration_s`, `crow_frac`, full-file pooling) does not match per-region inference (`3–9s` spans); per-region accuracy has not been evaluated.
- **BirdNET hears background habitat.** Full-clip embeddings (0.840 macro AUC) edge out clean crow-only windows (0.811), confirming that background soundscape adds a small boost when unmasked.
- **Macaulay dominates the strict subset** (`n=139` of 144) because Xeno-canto has far fewer American Crow remarks with witnessed predator triggers.

## What it changed

- **Replaced the assumption that archive data can't feed Problem 2 (semantics).** Free-text remarks already in `data/corvid.db` yielded **561 witnessed American Crow recordings (~18 hours)** (580 after pass-2 terrestrial screening) across 10+ semantic contexts with zero fieldwork and zero crowdsourcing — 133× the current field-labeled audio volume.
- **Established a recording-level semantic benchmark — and identified the confounds that still need clearing:** 7-class witnessed semantic separation at **0.811 macro AUC** and strict zero-raptor recording-level owl-vs-hawk separation at **0.769 AUC** (`p = 0.005`, metadata null 0.469, density-matched 0.667), while revealing that unmasked bystander species, predator posture, and recording-level chorus density remain confounded with predator identity.
- **Flagged begging as recoverable from archive remarks:** 77 witnessed American Crow begging clips (67 crow-detected, 451.1 min total, **0.963 OvR AUC**) are immediately usable to bolster the weak begging class without waiting on seasonal fledglings.
- **Documented why the first 4-class threat head is NOT ready to ship:** On the 378-clip archive it reached **0.757 macro AUC** (`owl` 0.859, `hawk` 0.685, `terrestrial` 0.653), but held-out verdict precision was weak (`owl` 51/90, `hawk` 20/51, `terrestrial` 2/21) and zero-shot Poe Family validation was null (`0.683` AUC on hand-picked 7 vs. 9 captures, `p = 0.243`, `7/29` hawk false alarms, `0/7` stranger captures reaching a terrestrial verdict).
- **Added `labels.json`** (portable Xeno-canto + Macaulay semantic labels), `threat_metrics.json`, `perch_threat_metrics.json`, and `crowgpt.progress.Run`-instrumented scripts as the baseline for Experiment `0103`.
