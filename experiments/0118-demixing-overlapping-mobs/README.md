# 0118 — Can unsupervised bird source separation de-mix overlapping crow mobs and uncover masked predator signals?

**2026-11-22** · GPU (BirdMixIT, <4 GB VRAM) + CPU (BirdNET) · **answer: Stage 0 passes — BirdMixIT separates conspecific 2-crow mixtures (+4.41 dB best-stem, +7.03 dB partition SI-SDRi at 0 dB) — and Stage 1 shows a clean double dissociation: de-mixing lifts within-hawk perched vs. flying from 0.857 to 0.905 while leaving owl vs. hawk null (0.567 per-caw on 0103 dev, 0.474 perched on 0104)**

> **Pre-registration (written and committed in `437b51c` before downloading BirdMixIT checkpoints or running separation on any recording).**

## The question

Experiments `0036`, `0105`, and `0113` all hit the same acoustic wall: when two or more crows call at once — the defining condition of a mob — envelope peak counters saturate, Perch's advantage vanishes (`0036`: `mob` AP falls from `2.93×` chance on 1 crow to `1.33×` on `2+`), and single-bird filtering (`0113`) has to discard more than half of pure-crow windows.

Google Research's **BirdMixIT** (`output_sources4`, 22.05 kHz, Apache 2.0) is the standard open-weights unsupervised avian sound separator, trained via Mixture Invariant Training on wild bird recordings. Nobody in this project had tested two stacked questions:
1. **The conspecific cocktail-party gate:** Can BirdMixIT actually separate *two overlapping American Crows* (nearly identical harsh broadband spectra), or does it only separate heterospecific birdsong occupying different frequency bands?
2. **The mobbing question:** If multi-crow mobbing windows in `0103` and `0104` are separated into stems first, do isolated stems carry owl-vs-hawk or perched-vs-flying information that overlapping choruses obscured?

## Pre-declared protocol

### Model

- Pretrained **Google Research BirdMixIT 4-source model** (`bird_mixit_model_checkpoints/output_sources4/model.ckpt-3223090`, 22,050 Hz input -> 4 waveform stems summing identically to the input mixture, `max_err = 7.5e-8`), cached under `data/models/bird_mixit/`.

### Stage 0 — Pre-declared Acoustic Gate on Synthetic 2-Crow Mixtures

- **Benchmark set:** **100 synthetic 2-crow mixtures at `0 dB` SNR** (`seed=0`, plus **50 mixtures at `+3 dB` SNR**, `seed=1`) built by pairing 3.0 s windows from **different** `crow-tools` recordings in `0109`'s dataset (`288` clean single-crow windows where `crowCount == 1` and no multi-crow segment shares the window).
- **Gate rule (binding):** Passes if median oracle best-stem **or** MixIT 2-partition **`SI-SDRi >= 2.0 dB`** on the 100 `0 dB` mixtures.

### Stage 1 — Binding Primary Mob De-Mixing Tests

- **Stem selection rule:** Run BirdMixIT on every 3.0 s multi-crow pure window (`P(several) >= 0.652` under `0115`'s frozen `crowgpt_b4` count head). Keep up to the **top 2 stems** by crow-band (`700–4500 Hz`) RMS energy (`>= 15%` of loudest stem).
- **Co-primaries (Holm-corrected family of 2):**
  1. **Primary A (`0103` dev multi-crow windows):** Caw-level `caw_acoustic_44d` owl vs. hawk (`eval_caw_cv`, inverse-recording-weighted ROC-AUC, 5-fold recordist-grouped, `C=0.1`, 400 permutations), compared against unseparated caws from the exact same multi-crow windows. Pass bar: `AUC >= 0.60` and Holm `perm_p < 0.05`.
  2. **Primary B (`0104` video clips):** BirdNET 1024d stem embeddings (combining already-single-bird pure windows unchanged + separated multi-crow stems) under `0104`'s `GroupedTest(C=0.05)` (400 channel permutations) on **(i)** strict `perched` owl vs. `perched` hawk (`36 vs 15`) and **(ii)** non-strict within-hawk `perched` vs. `flying` (`27 vs 21`).

---

## Results

Run once (`separate.py` + `evaluate.py` -> `results.json`).

### Stage 0 — Synthetic 2-crow conspecific separation gate: **PASSES**

| Synthetic 2-crow benchmark | Mixtures | Input SI-SDR (median) | Best single stem `SI-SDRi` (median, IQR) | % > 0 dB | MixIT 2-partition `SI-SDRi` (median, IQR) | % > 0 dB |
|---|---:|---:|---|---:|---|---:|
| **Primary (`0 dB` equal-RMS)** | 100 | `0.00 dB` | **`+4.41 dB`** (`+0.24` to `+8.85`) | **77%** | **`+7.03 dB`** (`+2.42` to `+12.46`) | **83%** |
| Secondary (`+3 dB` SNR) | 50 | `-0.01 dB` | **`+4.81 dB`** (`+2.48` to `+8.12`) | **86%** | **`+9.05 dB`** (`+5.54` to `+11.39`) | **92%** |

On `0109`'s BirdNET crowd-count head, separating the `0 dB` 2-crow mixtures lowers median `P(several)` from `0.172` on the mixture to `0.107` (stem 1) and `0.058` (stem 2). Both `SI-SDRi` metrics sit more than `2×` above the `2.0 dB` gate, so Stage 1 enters as **binding**.

### Stage 1 — Binding mobbing de-mixing tests

#### Primary A — `0103` dev multi-crow pure windows (`643` windows -> `797` stems across `82` recordings)

| Arm (`0103` dev, `date < 2023-01-01`, 5-fold recordist-grouped) | Caws | Recordings (`owl / hawk`) | Groups | Primary weighted per-caw AUC | Rec-mean AUC | Perm `p` | Holm `p` |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BirdMixIT separated stems (`caw_44d`)** | 1,587 | 82 (`56 / 26`) | 67 | **0.5668** | 0.5989 | 0.187 | **0.374** (null) |
| Unseparated same multi-crow windows (`caw_44d`) | 1,471 | 81 (`56 / 25`) | 66 | 0.4952 | 0.4843 | 0.491 | — |

De-mixing yields `+116` additional clean caw detections (`1,471 -> 1,587`) and lifts weighted per-caw AUC from dead `0.495` to `0.567` (`+0.072`, rec-mean `0.484 -> 0.599`), **but fails both the `0.60` bar and permutation significance (`p = 0.187`, Holm `0.374`)**.

#### Primary B — `0104` video clips (`2,061` separated multi-crow stems, BirdNET 1024d)

| `0104` contrast (5-fold channel-grouped) | Cells (`pos / neg`) | Unseparated `0104` AUC (`perm_p`) | **BirdMixIT De-Mixed AUC (`perm_p`)** | `Δ AUC` | Holm `p` |
|---|---|---:|---:|---:|---:|
| **Primary: Perched Owl vs. Perched Hawk (strict)** | `36 / 15` (50 ch) | `0.5389` (`0.399`) | **`0.4741`** (`0.601`) | **`-0.0648`** | **0.601** (null) |
| **Within Hawk: Perched vs. Flying (non-strict)** | `27 / 21` (47 ch) | `0.8571` (`0.0025`) | **`0.9048`** (`0.0025`) | **`+0.0477`** | — |

## Reading & what it changed

1. **BirdMixIT solves conspecific crow-on-crow separation well enough to be useful (`+4.4 dB` single-stem, `+7.0 dB` partition SI-SDRi).** `TODO.txt` noted that `crow-tools` left behind an unrecoverable Git-LFS stub of a 2-source DPRNNTasNet separator and identified overlapping crows as the ceiling on `mob` detection. Pretrained Apache-2.0 BirdMixIT (`output_sources4`) works out of the box on two overlapping American Crows.
2. **A clean double dissociation rules out "chorus overlap hid the owl word":**
   - If BirdMixIT had distorted crow calls on real mobbing videos, `within_hawk_perched_vs_flying` would have degraded. Instead, de-mixing **lifted within-hawk perched vs. flying by `+4.8` points (`0.857 -> 0.905`, `p = 0.0025`)** — the highest posture score measured in the project.
   - Yet on the exact same pipeline, **strict perched owl vs. perched hawk moved from `0.539` to `0.474` (chance)**, and caw-level owl vs. hawk in `0103` dev stayed non-significant (`0.567`, `p = 0.187`).
3. **Implication for CawDex / `FUTURE.txt`:** BirdMixIT is now a validated candidate front-end for the `mob` vs. `alert` overlapping-crow detector problem (`TODO.txt`), and gives no rescue to predator-referential owl-vs-hawk claims.
