# 0103 — Does owl vs. hawk mobbing survive caw-level segmentation, all-species bystander masking, and predator posture control?

> **Pre-registration notice (written before running any C, D, or E classifier or viewing any results):**
> All primary feature sets, primary metrics, masking rules, controls, and the temporal holdout cutoff (`2023-01-01`) below were fixed *before* extracting features, coding posture, or running any model. Any additional feature set or diagnostic reported later is explicitly labelled **exploratory**.

## Questions

Experiment `0102` established a recording-level owl-vs-hawk difference (`0.769` ROC-AUC on strict zero-raptor recordings), but an independent audit identified three unresolved confounds:
1. **Recording-level chorus vs. single caw:** `0102` pooled whole recordings, where chorus density (`crow_frac`, duty cycle, duration) alone scored `0.72`. Does an **individual segmented crow caw** carry owl vs. hawk information?
2. **Unmasked bystander species:** `0102` masked only raptors (`conf >= 0.05`), leaving woodland owl-mob bystanders (Blue Jays, Steller's Jays, chickadees, songbirds) unmasked inside 3s BirdNET windows.
3. **Predator posture confound:** Owls are almost always mobbed while perched, whereas hawks are often mobbed in flight. Does owl vs. hawk survive when restricted strictly to **perched** predators in the Xeno-canto + Macaulay archive?

## Pre-declared protocol

### Step E — Untouched temporal holdout (locked first in `holdout_2023.json`)
- **Cutoff:** Every strict zero-raptor American Crow `owl_mobbing` / `hawk_mobbing` recording in `0102/labels.json` with recording date **`>= 2023-01-01`** is sealed untouched (`n = 42`: 18 owl, 24 hawk). All cross-validation, matching, and diagnostics run strictly on **`date < 2023-01-01`** (`n = 106`: 61 owl, 45 hawk).
- **Single-shot test:** Final models from C and D are fit once on `date < 2023-01-01` and evaluated **exactly once** on `date >= 2023-01-01` at the end.

### Step C — Caw-level owl vs. hawk with all-non-crow masking
- **Strict pure-crow masking rule:** Keep only 3s BirdNET windows (`min_conf = 0.05`) where American Crow (`American Crow` / `Northwestern Crow`) is detected at `conf >= 0.25` **and zero non-crow species** are detected anywhere in that 3s window at `conf >= 0.05` (masking every raptor, jay, songbird, human, and other non-crow species). Recordings must also satisfy `pred_vocal = false` and `max_raptor_conf < 0.05` everywhere.
- **Individual caw segmentation:** Deterministic crow-band (`700–4500 Hz`, 22050 Hz) RMS envelope peak finder inside pure-crow windows (min spacing `180 ms`, prominence `>= 0.15`, onset/offset at `25%` peak height, duration `80–700 ms`, up to 30 highest-SNR caws per recording).
- **Pre-declared primary feature set:** `caw_acoustic_44d` — 44 per-caw waveform features extracted strictly inside `[onset, offset]` on unit-RMS peak-normalized `600–5000 Hz` audio (duration, attack fraction, peak/mean RMS, YIN F0 median/IQR/slope/voiced fraction, spectral centroid/std/bandwidth/rolloff/flatness/ZCR, harmonic ratio, low-mid ratio, 13 MFCC means + 13 MFCC stds, 3 sub-band energy ratios). Zero recording-level density, duration, or BirdNET context features.
- **Pre-declared primary metric:** **Inverse-recording-weighted per-caw ROC-AUC** (`StandardScaler` + `LogisticRegression(C=0.1, solver="liblinear", class_weight="balanced")`) under **5-fold `StratifiedGroupKFold` holding out whole recordings by recordist**, evaluated on:
  1. Full pure-crow dev set (`date < 2023-01-01`), with 400-shuffle recordist-level permutation test and metadata-only null (`duration_s`, `lat`, `lng`, `month_sin/cos`, `hour_sin/cos`, `source`).
  2. 1-to-1 **density-matched** dev subset (matched on recording `crow_frac`, `duty_cycle`, and `n_pure_crow_windows`).
- **Explicitly exploratory diagnostics:** (i) Unweighted per-caw AUC & recording-averaged caw AUC; (ii) `birdnet_isolated_caw_1024d` (isolated `[onset-20ms, offset+20ms]` caw zero-padded to 3.0s with 10 ms fades); (iii) recording-level BirdNET mean embedding on strictly pure-crow windows (testing whether bystander masking alone eliminates 0102's 0.769).

### Step D — Archive predator posture control (`perched` vs. `flying`)
- **Blind remark coding:** Re-read every strict owl/hawk remark in `0102/labels.json` (`n = 148`, blind to audio and split) and code predator posture into `perched`, `flying`, `mixed`, or `unknown` (`posture_labels.json`).
- **Pre-declared primary subset:** Strictly `posture == "perched"` + zero-raptor + pure-crow windows (`date < 2023-01-01`).
- **Pre-declared primary feature set & metric:** **Recording-level BirdNET mean embedding (1024d) on strictly pure-crow windows, 5-fold recordist-grouped ROC-AUC** (`StandardScaler` + `LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced")`) with 400-shuffle recordist-level permutation test and metadata-only null.
- **Explicitly exploratory diagnostics:** Caw-level `caw_acoustic_44d` restricted to `perched` dev clips, and `perched` vs. `flying` within `hawk_mobbing`.

---

## Results

### Step C — Caw-level owl vs. hawk with all-non-crow masking (Dev, `date < 2023-01-01`)

Across all 106 strict zero-raptor dev recordings, masking every 3s window with *any* non-crow BirdNET detection (`>= 0.05`) retained **101 pure-crow recordings** (`61 owl_mobbing`, `40 hawk_mobbing`) and **2,150 segmented individual caws** across **100 recordings** (`60 owl`, `40 hawk`, `82` recordists).

| Test (Dev, `date < 2023-01-01`, 5-fold recordist-grouped CV) | Scope | Primary metric (`w_per_caw_AUC`) | Perm `p` (400 shuffles) | Exploratory: `unw_caw` / `rec_mean` |
|---|---|---:|---:|---:|
| **PRIMARY: `caw_acoustic_44d` (full pure-crow dev)** | 2,150 caws, 100 recs (60/40), 82 groups | **0.5156** | **0.4090** (null) | 0.4692 / 0.5242 |
| **PRIMARY: `caw_acoustic_44d` (density-matched dev)** | 1,589 caws, 76 recs (38/38; cov AUC 0.540) | **0.5969** | **0.0773** (null) | 0.5331 / 0.6177 |
| Metadata-only null (`duration, lat, lng, month, hour, src`) | 100 recs (60/40) | 0.4704 | — | — |
| *Exploratory:* isolated-caw BirdNET `1024d` (full dev) | 2,150 caws, 100 recs | 0.5223 | 0.2836 (null) | — / 0.5442 |
| *Exploratory:* isolated-caw BirdNET `1024d` (density-matched) | 1,589 caws, 76 recs | 0.5710 | 0.1343 (null) | — / 0.6295 |

**Per-fold dev diagnostic (`caw_acoustic_44d`):** Across the 5 recordist-grouped dev folds (`n=19–21` recs/fold), fold weighted per-caw AUCs were `0.498, 0.578, 0.355, 0.610, 0.553` (mean `0.519`). **Step C on dev is a null result.**

**Exploratory bystander-masking diagnostic (recording-level BirdNET mean, same `n = 101` pure-crow dev recordings):**
- Raptor-masked only (`0102`-style): `0.6512` (`perm_p = 0.0498`)
- **All-non-crow masked** (zero non-crow BirdNET species `>= 0.05`): **`0.6385` (`perm_p = 0.0574`)** (`-0.013` shift)
- All-non-crow masked + 1-to-1 density-matched (`n = 76`): **`0.6683` (`perm_p = 0.0399`)**
- Top non-crow BirdNET detections inside crow windows were look-alike corvid confusions (*Fish Crow*, *Rook*, *Carrion Crow*, *Common Raven*, *Large-billed Crow*), not woodland jays/songbirds. Masking every non-crow BirdNET species did **not** erase the recording-level difference on dev.

---

### Step D — Archive predator posture control (`posture_labels.json`)

Blind coding of all 148 strict zero-raptor owl/hawk remarks (blind to audio and recording date) yielded:

| Context | `perched` | `flying` | `mixed` | `unknown` | Total |
|---|---:|---:|---:|---:|---:|
| `owl_mobbing` | **16** | **2** | 5 | 56 | 79 |
| `hawk_mobbing` | **12** | **18** | 6 | 33 | 69 |
| **Total** | **28** | **20** | **11** | **89** | **148** |

**Key empirical findings on posture:**
1. **Severe posture confound confirmed:** Among posture-explicit remarks, owls are **89% perched** (`16:2`) while hawks are **60% flying** (`12:18`).
2. **Small perched sample size:** Because 89/148 archive remarks do not state posture (`unknown`), explicitly perched strict clips total only **28** across the entire archive (`20` pure-crow in dev: `12 owl / 8 hawk`, and `6` in holdout: `4 owl / 2 hawk`) — far below the hundreds needed for a high-power perched-only archive test.

| Test (Dev, `date < 2023-01-01`, 5-fold recordist-grouped CV) | Scope | ROC-AUC | Perm `p` | Metadata null |
|---|---|---:|---:|---:|
| **PRIMARY: `perched` + pure-crow BirdNET mean (1024d)** | `n = 20` (12 owl / 8 hawk, 19 groups) | **0.4896** | **0.4439** (null) | 0.6458 |
| *Exploratory:* `perched` + raptor-masked-only BirdNET mean | `n = 22` (12 owl / 10 hawk) | 0.5917 | 0.2070 (null) | — |
| *Exploratory:* `perched` `caw_acoustic_44d` (weighted per-caw) | 335 caws, 19 recs | 0.4325 | 0.5860 (null) | — |
| *Exploratory:* `perched` isolated-caw BirdNET | 335 caws, 19 recs | 0.5110 | 0.5174 (null) | — |
| *Exploratory:* within-`hawk_mobbing` perched (8) vs. flying (10) | `n = 18` (17 groups) | 0.6250 | 0.3184 (null) | — |

**Step D on dev is a null result** (and underpowered at `n = 20`).

---

### Step E — Single-shot final evaluation on untouched temporal holdout (`date >= 2023-01-01`)

Models from Steps C and D were fit **once** on `date < 2023-01-01` and evaluated **exactly once** on the untouched `2023–2026` holdout (`n = 32` pure-crow recordings: `17 owl`, `15 hawk`, `718` caws; zero-recordist-overlap subset `n = 26`: `15 owl`, `11 hawk`, `559` caws):

| Test (Untouched holdout `date >= 2023-01-01`) | Scope | Primary metric | Rec-mean AUC (`MW 2-sided p`) | Zero-recordist-overlap |
|---|---|---:|---:|---:|
| **Step C PRIMARY: `caw_acoustic_44d`** | 718 caws, 32 recs (17/15) | **0.7198** | 0.8431 (`p = 0.0010`) | **0.7208** (rec-mean 0.8485, `p = 0.0031`) |
| **Step D PRIMARY: `perched` + pure-crow BirdNET mean** | `n = 6` (4 owl / 2 hawk) | **0.5000** | — (`p = 1.000`, null) | 0.3333 (`n = 5`, `p = 0.800`) |
| *Exploratory:* isolated-caw BirdNET `1024d` | 718 caws, 32 recs (17/15) | 0.7148 | 0.8824 (`p = 0.0002`) | — |
| *Exploratory:* recording-level pure-crow BirdNET mean | 32 recs (17/15) | 0.7922 | — (`p = 0.0052`) | 0.7394 (`n = 26`, `p = 0.0430`) |
| *Exploratory:* `perched` + raptor-masked-only BirdNET | `n = 6` (4 owl / 2 hawk) | 0.7500 | — (`p = 0.533`, null) | — |

## Honest interpretation & what it changed

1. **Do NOT claim single-caw owl-vs-hawk decoding is solved.** Although the untouched `2023–2026` holdout yielded a striking single-shot result on both `caw_acoustic_44d` (`0.720` weighted per-caw, `0.843` rec-mean, `p = 0.001`) and isolated-caw BirdNET (`0.715` per-caw, `0.882` rec-mean, `p = 0.0002`), the **pre-declared dev CV (`date < 2023-01-01`, `n = 100`) was null** (`0.516, p = 0.409` full; `0.597, p = 0.077` density-matched), and **perched-only owl vs. hawk was null on both dev (`0.490, p = 0.444, n = 20`) and holdout (`0.500, n = 6`)**.
2. **Why did holdout beat dev CV?** Two likely factors, neither of which proves posture-independent predator identity:
   - **Audio-era homogeneity:** Dev `< 2023` includes 8 pre-2015 legacy tape/archive recordings and heterogeneous older microphones (with wide fold variance `0.355–0.610`), whereas `2023–2026` is uniformly modern digital Macaulay audio.
   - **Unresolved posture confound in the holdout:** In `2023–2026`, posture-explicit holdout hawks are **7 flying / 2 perched** while owls are **4 perched / 1 flying**. Even an isolated single caw uttered during an intense stationary perched-owl mob vs. a brief aerial hawk chase can reflect **arousal/posture/mobbing intensity**, not predator-referential semantics.
3. **What IS now ruled out:** Non-crow bystander species (jays, songbirds) are **not** what drives `0102`'s recording-level owl-vs-hawk separation. Masking every non-crow BirdNET species (`>= 0.05`) left dev recording-level BirdNET nearly unchanged (`0.651 → 0.639`, density-matched `0.668, p = 0.040`) and held at `0.792` (`p = 0.005`) on the untouched `2023–2026` holdout.
4. **Conclusion for now:** The evidence supports **"crows mob mostly-perched owls harder and differently than mostly-flying hawks, detectable even after masking all non-crow species — and on modern 2023+ digital recordings, even from isolated caws"** — but **does NOT yet prove perched-matched, predator-specific single-caw semantics**, and **nothing should ship into `analyzer/`** until a well-powered perched-only corpus resolves the posture confound and achieves usable operating-point precision.

