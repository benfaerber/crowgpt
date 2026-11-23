# 0119 — Do crow calls predict what happens next?

**2026-11-22** · CPU · **answer: no across all three call-level pragmatics tests — single-bird recruitment (0.549, Holm p = 0.219) and parental begging-cessation call acoustics (0.577, Holm p = 0.219) are null; within-recording terminal calls before silence pass on fixed 3 s BirdNET windows (0.770, Holm p = 0.0075) solely because BirdNET reads where inside the 3 s frame the bout starts vs. ends (0.749 phase-only), while the isolated caw itself sits at dead chance (0.490 BirdNET, 0.483 waveform)**

> **Pre-registration (written and committed in `4aec1a1` before scanning candidate windows, forming transition labels, or computing any rate or AUC).**

## The question

Experiments `0102`–`0118` tested **simultaneous** scene labels — what predator, posture, or context a human observer noted during a recording — and found that predator species nouns (`owl` vs. `hawk`) sit at chance once posture is held fixed (`0.35–0.62`), while threat posture (`perched` vs. `flying`, `0.81–0.905`) and broad behavioral context (`0.65–0.80`) are readable.

As `TODO.txt` (*"Nothing can record what a call achieved"*) points out, simultaneous tags cannot test **pragmatics** — what changed *after* a call:
1. **Recruitment:** When a single crow calls with no crowd present, does anything in its call predict that a multi-bird crowd arrives over the next 18 seconds?
2. **Abrupt cessation / scatter:** Inside the same recording and microphone, does the final single-bird call before `>= 15 s` of verified live-mic silence differ acoustically from an earlier single-bird call followed by continued calling — *beyond* simple loudness/SNR fade as a bird moves away from the microphone?
3. **Parental intervention / begging cessation (Capture 104 hypothesis):** Capture 104 (`field.db` `id = 104`) recorded a fledgling begging, an adult calling once (begging continued), and the adult calling a second time ("harder"), after which begging stopped for the remaining 13.5 s of the file. Across hundreds of begging recordings in `corvid.db`, do interspersed non-begging adult calls precede begging cessation above baseline, and does the adult call's acoustics predict whether begging stops vs. continues?

All three questions generate their own time-locked `before -> focal call -> after` labels directly from the `22,768` BirdNET-analyzed American Crow recordings already on disk in `data/corvid.db`, requiring zero new fieldwork.

---

## Pre-declared protocol

### Corpus pool, deduplication, and observer grouping

- **Eligible files:** Downloaded, analyzed `american-crow` recordings in `data/corvid.db` with verified audio duration **`24.0 s <= duration <= 300.0 s`** (`>= 31.0 s` general pool plus `24.0–31.0 s` begging-flagged files) containing at least one corvid detection (`5,161` deduplicated recordings scanned across 12 CPU workers, `0` scan failures).
- **Deduplication:** Deduplicated by `content_sha256` (keeping lowest `recordings.id`).
- **Observer grouping:** All cross-validation folds, bootstraps, and label permutations group strictly by `observer = group_key or normalized_recordist or f"rec:{id}"`.

### Window scan and live-mic tail gate

Every candidate recording was scanned on a non-overlapping **3.0 s grid** (`scan.py`, `min_conf = 0.05`, reusing `0112`'s cached BirdNET detections/embeddings where available) alongside 22,050 Hz waveform envelope statistics per 3.0 s window: `rms_db`, `crow_rms_db` (`700–4500 Hz`), `noise_p10_db` (10th-percentile 50 ms frame dBFS), `snr_db = crow_rms_db - noise_p10_db`, `duty_u` (`0107` duty cycle), and `zero_frac` (`|x| < 1e-5`).

**Live-mic tail gate (`live_tail(t0, t1)`):** Any post-call observation span `[t0, t1]` had to satisfy (1) `t1 <= file_duration - 1.0 s`, (2) `zero_frac < 0.05` on every 3 s window (no digital silence, truncation, or mute), and (3) `median(noise_p10_db in [t0, t1])` within `[-6.0 dB, +6.0 dB]` of the recording's pre-focal `noise_p10_db` median (rejecting fade-outs, gain cuts, and mic shutoffs; rejected `1,593` noise-floor shifts and `1,196` dropout spans across the three screens).

### Frozen reference heads and thresholds (fixed on `0109` / `0111` before touching `0119` windows)

- **Crowd head (`P_several`, `0109`):** `T_single = 0.5826` (`90.04%` one-crow precision, `87.91%` recall on `0109`'s hand-labelled segments); `T_crowd = 0.9236` (`80.13%` multi-crow precision, `44.10%` recall, `317` OOF segments).
- **Begging head (`S_beg`, `0111`):** `S_beg >= 0.0` active-begging boundary (`1.0%` winter false alarms in `0111`), `T_beg = -2.0026` (`90%` archive begging recall) used both as the sensitive check for lingering post-call begging and as `S_beg < T_beg` to guarantee an interspersed adult call is genuinely non-begging.

### Co-primary tests (Holm–Bonferroni corrected family of 3)

All three cleared the `>= 20` per-class floor and entered the Holm family (`StandardScaler + LogisticRegression(C=0.05, balanced)`, 5-fold observer-grouped CV, `>= 0.65` residualized AUC + Holm `p < 0.05` pass bar):
1. **Primary A — Single-Bird Recruitment (`Solo -> Crowd` vs. `Solo -> Solo`):** Pure single-crow focal window `[t, t+3]` (`t >= 6 s`, zero multi-crow or raptor windows in `[t-9, t]`, valid `live_tail(t+3, t+24)`) followed by `>= 2` crowd windows (`P_several >= 0.924`) in `[t+6, t+24]` vs. zero `>= T_single` windows in `[t+3, t+24]` (`4×` negative cap, `seed=0`); `[P_several, duty_u, crow_rms_db, snr_db]` regressed out in-fold.
2. **Primary B — Within-Recording Abrupt Cessation (`Continuing` vs. `Terminal` Single-Bird Call):** Strictly 1 matched pair per recording: earliest pure single-crow window `[t_cont, t_cont+3]` (`<= t_stop - 12 s`) followed by `>= 2` crow windows in `[t_cont+3, t_cont+18]`, paired against the final pure single-crow window `[t_stop, t_stop+3]` followed by `15 s` of verified live-mic silence (`max corvid < 0.10`, `mean duty_u < 0.05`); `[crow_rms_db, snr_db, P_several, duty_u]` regressed out in-fold, 400 within-recording sign-flip permutations.
3. **Primary C — Parental Call Acoustics Before Begging Cessation:** Interspersed non-begging crow window (`american_crow >= 0.25`, `raptor < 0.05`, `S_beg < -2.003`) after active begging in `[t-12, t]`, predicting zero begging in `[t+3, t+18]` (`stopped = 1`) vs. `>= 2` begging windows (`continued = 0`); `[crow_rms_db, snr_db, P_several, S_beg]` regressed out in-fold.

---

## Results

Run once (`scan.py` + `run.py` -> `results.json`), followed by a post-hoc forensic check (`audit.py` -> `audit_results.json`) explaining the 29-point gap between Primary B's 3 s BirdNET window score and its single-caw score.

### Co-primary summary

| Co-primary test | Sample (observers) | Residualized BirdNET 3 s AUC (95% CI) | Raw BirdNET AUC | Nuisance-only AUC | Single-caw `caw_44d` AUC | Holm `p` | Pre-reg rule |
|---|---|---:|---:|---:|---:|---:|---|
| **Primary A:** Single-bird recruitment (`Solo -> Crowd`) | `75` pos / `300` neg (`368` obs; `1,373` total neg) | **0.5489** (`0.471–0.623`) | 0.5896 | **0.6686** | 0.5721 | **0.219** | **NULL** |
| **Primary B:** Within-recording cessation (`Continuing` vs. `Terminal`) | `146` pairs = `292` wins (`143` obs) | **0.7703** (`0.722–0.816`) | 0.7695 | 0.5367 | **0.4825** | **0.0075** | Passes on 3 s grid; **see phase audit below (isolated caw = `0.490`)** |
| **Primary C:** Adult call acoustics before begging stops | `50` stop / `188` cont (`221` obs) | **0.5765** (`0.476–0.671`) | 0.6151 | 0.5945 | 0.4531 | **0.219** | **NULL** |

---

### Deep dive & forensic audits

#### 1. Primary A (Recruitment): Pre-existing distant crowd carries the naive signal, not the focal caw
- Even inside pure single-bird windows (`P_several < 0.583`), recordings where a crowd arrives in `[t+6, t+24]` already had higher residual `P_several` (`0.169` vs. `0.026` median) and higher `snr_db` (`9.69` vs. `7.31 dB`) at `[t, t+3]`, giving the 4-number nuisance baseline **`0.6686` AUC** on its own.
- Once those nuisance terms are regressed out inside each fold, BirdNET drops to **`0.5489` (`Holm p = 0.219`)**, and isolated single-caw features (`caw_44d`, `n = 367`) score **`0.5721`** (`caw_dur_s` `0.223` vs. `0.218 s`, `f0_med_hz` `1424` vs. `1397 Hz`; only `caw_rate_hz` shows a slight positive shift, `SMD = +0.40`).

#### 2. Primary B (Abrupt Cessation): Why 3 s BirdNET scored `0.770` while the caws themselves scored `0.483` / `0.490`
- **`S_B1` ("Bird flew away" loudness check):** Terminal windows before silence are only marginally quieter than earlier continuing windows in the same recording (`median ΔSNR = -1.00 dB`, Wilcoxon `p = 0.077`; `median Δcrow_rms = -0.62 dB`, `p = 0.382`), so simple amplitude fade was weak (`nuisance_only_auc = 0.537`).
- **The glaring discrepancy:** Pre-declared `S_caw44` segmented the caws inside the exact same `140` pairs and scored **`0.4825` AUC** — identical median caw duration (`0.2145 s` vs. `0.2145 s`), median F0 (`1366 Hz` vs. `1384 Hz`), and caw count (`3.0` vs. `3.0` caws, BirdNET `american_crow` confidence `0.918` vs. `0.911`).
- **Post-hoc audit (`audit.py`):** Inspecting *where* inside the fixed `3.0 s` `[0, 3.0]` STFT grid the caws fall resolved the entire `0.770` vs. `0.483` gap:

  | Diagnostic on the 146 within-recording pairs (`audit.py`) | Continuing window (`t_cont`) | Terminal window (`t_stop`) | OOF / Univariate AUC |
  |---|---:|---:|---:|
  | Segmented caw count / BirdNET `american_crow` conf | `3.0` / `0.911` | `3.0` / `0.918` | `0.482` / `0.484` |
  | Last caw offset inside `[0, 3.0 s]` window | **`2.68 s`** | **`1.81 s`** | **`0.240`** (`0.760` inverted) |
  | Second-half minus first-half crow-band dB (`h2 - h1`) | **`+3.62 dB`** (rises) | **`-5.36 dB`** (falls to silence) | **`0.243`** (`0.757` inverted) |
  | 8 within-window phase/envelope scalars alone (`Z_phase`) | — | — | **`0.7487`** |
  | BirdNET 3 s window with `Z_orig + Z_phase` regressed out | — | — | `0.6421` (below `0.65` bar) |
  | 3 s real-audio window right-aligned to `last_caw_offset + 0.10 s` (`102` pairs) | — | — | `0.6030` |
  | **Isolated last caw centered in 3 s zero buffer, BirdNET `1024-d` (`140` pairs)** | — | — | **`0.4898`** (dead chance) |

  Because `t_cont` selected the *earliest* qualifying single-crow window (often a bout onset where calling starts mid-window and continues across `t_cont + 3.0 s`) whereas `t_stop` is the *final* window before silence (where calling stops mid-window at median `1.81 s` and `[1.81, 3.00 s]` is already silent), **BirdNET's 1024-d CNN embedding is reading horizontal energy placement inside its 3 s spectrogram (`0.749` from phase scalars alone)**! When the last caw itself is cut out and centered identically in BirdNET, separation collapses to **`0.4898`**, matching `caw_44d`'s **`0.4825`**. Crows do **not** emit a distinct "termination / scatter" caw before falling silent.

#### 3. Primary C, `S_C1`, and Capture 104: Resolving the "Parental Shush" Hypothesis at Scale
- **Acoustics (`Primary C`):** Across `238` interspersed non-begging adult calls (`50` followed by `15 s` of zero begging vs. `188` followed by continued begging across `221` observers), neither residualized BirdNET (`0.5765`, `Holm p = 0.219`) nor `caw_44d` (`0.4531`) separates calls that precede silence from calls that do not.
- **Event rate (`S_C1`) and the silent-pause control (`audit.py`):**
  - Pre-declared `S_C1` compared begging cessation in `[t+3, t+18]` after an **adult non-begging window** (`405` checkpoints across `227` recordings) against an **ongoing begging window** (`1,866` checkpoints across `391` recordings): begging stopped **`14.81%`** of the time after an adult call vs. **`2.84%`** after ongoing begging (`Δ = +11.97%`, observer-bootstrap `95% CI: +8.03% to +16.39%`; `+11.99%` adjusted for recording position).
  - **Crucial post-hoc control (`audit.py`):** At an `adult_nonbeg` checkpoint (`S_beg < -2.00`), the fledgling has *already* paused begging during `[t, t+3]`. Checking the exact same `[t-12, t]` active-begging histories when `[t, t+3]` is a **3-second silent pause with NO crow calling at all (`corvid < 0.15`, `n = 836`)** yields a cessation rate of **`16.75%`** (`6.67%` when multiple birds overlap begging at `[t, t+3]`, `n = 90`).
  - **Verdict on Capture 104:** An adult calling during a 3 s pause in begging is followed by cessation **slightly less often (`14.81%`) than an ordinary 3 s pause with no adult call (`16.75%`)**. On out-of-sample Capture 104 (`S_104`), the adult call region at `42–51 s` (`s_beg = -2.38..-4.21`) was actually `-8 to -9 dB` quieter (`crow_rms_db = -61.5 dB`) than the fledgling's begging (`-52.5 dB`) and scored near zero (`-1.64` to `+0.07`) on the corpus-trained cessation head. Capture 104's sequence ("adult called harder -> begging stopped") does not generalize as a vocal "shush" across `471` observers in `corvid.db`.

---

## Limits

- `corvid.db` is observational audio without video: when calling stops for `>= 15 s` with a verified live microphone, audio alone cannot distinguish a raptor-triggered scatter freeze from a crow quietly perching or flying away silently — only that **the final caw before silence carries no acoustic signature (`0.490`)**.
- Primary A tests whether an *unremarkable lone crow's* call predicts crowd arrival across general recordings; true predator-discovery recruitment in nature may happen within the first seconds before a human recordist starts recording (consistent with `0115`'s S3 finding on archive mobbing clips).

## What it changed

1. **Settles the Capture 104 / outcome-tag schema question in `TODO.txt` (*"Nothing can record what a call achieved"*) -> do not build outcome links yet:** `TODO.txt` warned *"One recording is an anecdote, and a schema built from one is usually built wrong."* Across `5,161` recordings (`405` adult-call checkpoints, `836` silent-pause controls), adult calls during begging neither raise cessation above a plain 3 s pause (`14.8%` vs. `16.8%`) nor differ acoustically when begging stops (`0.577` / `0.453`). Keep unusual sequences in free-text notes rather than adding `other_bird_fell_silent` or response-link tables to `fieldserver/` and `mobile/`.
2. **Documents a new BirdNET representation trap (`3 s` within-window phase leakage):** BirdNET's `1024-d` vector is **not shift-invariant inside its 3.0 s window** — bout-onset windows (energy in `[1.5, 3.0 s]`) vs. bout-offset windows (energy in `[0, 1.5 s]`) separate at **`0.749–0.770` AUC** even when caw count, confidence, duty cycle, and isolated-caw BirdNET embeddings (`0.490`) are identical. Any future boundary or transition test using BirdNET embeddings must align windows to segmented call offsets or embed isolated calls.
3. **Closes the observational audio-only search for hidden semantic/pragmatic caw types (`0102`–`0119`):** Across predator nouns (`0103`–`0118`) and time-locked call consequences (`0119`), individual caws do not carry discrete lexical words for owl vs. hawk, "come here", "scatter", or "stop begging". What crow calling reliably encodes in audio is **broad behavioral context (`begging`, `mobbing`, `roost`, `flight`), caller/crowd density (`0109`/`0112`), graded prosody (`0113`), and threat engagement/posture (`perched` vs. `flying`, `0.81–0.905`)**.
