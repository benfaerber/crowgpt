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
2. **Not purely alarm-vs-non-alarm or geography:** Within strongly alarming clips (`p(alarm) >= 0.5`), BirdNET still separates owl from hawk at **0.711 AUC**; within Eastern US clips only (`lng > -95`), **0.750 AUC**; and stripping duration, `crow_frac`, and loudness still leaves **0.663 AUC** in spectral/MFCC prosody.
3. **Sub-trigger surprise — Great Horned Owl vs. Barred Owl:** Within strict owl clips (`n=70`, 53 GHO vs. 17 Barred, 57 recordists), BirdNET reaches **0.787 AUC** and pure prosody reaches **0.773 AUC** (while longitude alone is 0.369 and metadata is 0.600; median `p(alarm)` is 0.984 for GHO vs. 0.899 for Barred). Conversely, Red-tailed vs. Cooper's/Red-shouldered Hawk is null (**0.405 AUC**, `n=40`).

### 3. Confounded null: All-Corvus aerial predator vs. mammal scold

BirdNET scored **0.869 AUC** (`n=197`, 24 mammal vs. 173 owl/hawk), **but metadata alone scored 0.799 AUC** because mammal scolds in the archives come predominantly from European Hooded and Carrion Crows while owl/hawk clips are mostly North American American Crows. Treat cross-species aerial-vs-mammal as confounded until within-species mammal counts grow (currently only 9 American Crow).

## Caveats

- **Perched vs. aerial ecology remains entangled with predator identity.** Owls are usually mobbed while perched in cover by a dense stationary chorus, whereas hawks are often mobbed in flight or brief flybys. That ecological difference likely explains part of the intensity/persistence gap (`p(alarm)` 0.984 vs. 0.308), though the within-alarm separation (0.711), spectral-only prosody (0.663), and GHO-vs-Barred split (0.773 prosody AUC, both perched owls) suggest threat level or predator-specific vocal modulation beyond mere perched/flying geometry.
- **BirdNET hears background habitat.** Full-clip embeddings (0.840 macro AUC) edge out clean crow-only windows (0.811), confirming that background soundscape adds a small boost when unmasked. Always report crow-only masked windows and compare against prosody + metadata nulls.
- **Macaulay dominates the strict subset** (`n=139` of 144) because Xeno-canto has far fewer American Crow remarks with witnessed predator triggers.

## What it changed

- **Replaced the assumption that archive data can't feed Problem 2 (semantics).** Free-text remarks already in `data/corvid.db` yielded **561 witnessed American Crow recordings (~18 hours)** across 10+ semantic contexts with zero fieldwork and zero crowdsourcing — 133× the current field-labeled audio volume.
- **Established the first non-null, confounder-controlled semantic benchmark in the project:** 7-class witnessed semantic separation at **0.811 macro AUC** and strict zero-raptor owl-vs-hawk separation at **0.769 AUC** (`p = 0.005`, metadata null 0.469).
- **Flagged begging as recoverable from archive remarks:** 77 witnessed American Crow begging clips (67 crow-detected, 451.1 min total, **0.963 OvR AUC**) are immediately usable to bolster the weak begging class without waiting on seasonal fledglings.
- **Added `labels.json`** (portable Xeno-canto + Macaulay semantic labels) and a `crowgpt.progress.Run`-instrumented `run.py` so future embedders (CrowGPT hidden states, Perch, HuBERT) can be benchmarked directly on the same 561 witnessed semantic recordings.
