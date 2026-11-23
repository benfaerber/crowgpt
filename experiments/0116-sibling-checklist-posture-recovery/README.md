# 0116 — How many unknown raptor postures do sibling eBird checklists recover, and does perched owl vs. hawk move?

**2026-11-22** · eBird API v2 + CPU · **answer: checklists recover 63 postures and catch 22 unreported vocal raptors, leaving strict archive perched owl vs. hawk null (19 vs. 12: BirdNET 0.618, p = 0.18; Perch 0.504, p = 0.44) and pooled archive + video perched weak/null after Holm (55 vs. 27: BirdNET 0.661, Holm p = 0.25; Perch 0.593, p = 0.18) — while independently replicating within-hawk perched vs. flying in audio-only archive checklists (BirdNET 0.811, Perch 0.902 vs. 0.500 density null)**

> **Pre-registration (written and committed in `437b51c` before fetching any checklist, with blind labels frozen in `4fc940c` before `eval.py` ran).**

## The question

Experiment `0103` showed that predator posture confounds archive owl-vs-hawk comparisons (`16:2` perched for owls vs. `12:18` perched:flying for hawks), and left the perched-only test underpowered because **89 of 148** strict American Crow remarks did not state what the predator was doing (`unknown`). Experiment `0104` built a 310-video set (`36` perched owl vs. `15` perched hawk -> `0.539` AUC) and found **perched vs. flying within hawk at `0.857`**.

However, **213 unique `ebirdChecklistId`s (`S...`)** underlie `0102`'s 257 witnessed American Crow owl/hawk recordings in `corvid.db`. On eBird checklists, observers often describe what the hawk or owl was doing under **the raptor's own checklist row** or the **checklist-level comments**, neither of which appears in the American Crow audio's `mediaNotes`.

## Pre-declared protocol

1. **Checklist fetch & blind coding sheet:** Fetched all **213 unique eBird checklists** (`0` errors) via `/v2/product/checklist/view/{subId}` (`164/257` recordings carried checklist comments or sibling raptor observation notes/media counts). Extracted a text-only sheet (`blind_coding_sheet.json` under `data/`, no audio features, no model scores, no dates/splits).
2. **Blind coding & vocal-raptor hygiene (`4fc940c`):** Coded predator posture (`perched`, `flying`, `mixed`, `unknown`) strictly from the predator's described behavior (ignoring crow-side tags like `flying_flight`) and flagged `pred_vocal_checklist = true` whenever the sibling raptor row stated the raptor vocalized or carried an uploaded raptor audio recording (`mediaCounts.A > 0`). Frozen in `checklist_posture_labels.json` before `eval.py` ran.
3. **Primary test:** Strict zero-raptor, pure-crow (`american_crow >= 0.25`, `other < 0.05`, `raptor < 0.05`, `pred_vocal == False`, `pred_vocal_checklist == False`) **archive Perched Owl vs. Perched Hawk**, BirdNET 1024d mean over pure-crow windows, 5-fold recordist-grouped `StratifiedGroupKFold`, `C = 0.05`, 400 recordist permutations, beside density null (`duration_s, pure_crow_frac, n_pure_crow_windows`).

---

## Results

Run once (`results.json`).

### 1. What sibling eBird checklists changed in the data

- **63 previously-unknown postures recovered** across the 257 witnessed recordings: coded totals moved to `owl_mobbing` (`31 perched, 5 flying, 15 mixed, 71 unknown`) and `hawk_mobbing` (`17 perched, 31 flying, 23 mixed, 64 unknown`).
- **22 unreported vocalizing raptors caught (`pred_vocal_checklist = true`):** Sibling raptor checklist rows revealed 22 recordings where the observer noted the owl or hawk calling (or uploaded an audio recording of the raptor on the same checklist) without mentioning it in the crow's remark.
- **2 "perched" hawks in `0103` turned out to have flushed and chased (`mixed`):** Recordings `24663` and `32207` said *"in the tree"* on the crow remark, while the sibling hawk checklist comments described the hawk flushing and chasing in flight.
- Because removing newly caught vocal raptors and reclassifying those two flushed hawks offset the newly recovered perched hawks, strict pure-crow archive perched counts landed at **`19` owl vs. `12` hawk** (`30` recordists — still `< 15` in the hawk cell).

### 2. Primary & Secondary 1 — Strict archive Perched Owl vs. Perched Hawk (`n = 31`: `19` owl, `12` hawk, `30` recordists)

| Representation | ROC-AUC | Perm `p` (400 shuffles) | Holm `p` | Density null AUC | Verdict |
|---|---:|---:|---:|---:|---|
| **PRIMARY: BirdNET (1024d)** | **0.6184** | **0.1820** | — | 0.4386 | **NULL** (`< 15` hawks, underpowered) |
| **S1: Perch 2.0 (1536d)** | **0.5044** | **0.4414** | 0.456 | 0.4386 | **NULL (exact chance)** |
| **S1: CrowGPT block 4** | **0.6491** | **0.1521** | 0.456 | 0.4386 | **NULL** |
| *Sensitivity:* keeping `0103`'s 2 flushed (`mixed`) hawks as `perched` (`19 vs. 14`) | 0.7105 | 0.0499 | — | 0.5263 | Carried by the 2 chased-in-flight hawks |

Look at that sensitivity row: leaving the two hawks (`24663`, `32207`) whose sibling checklist comments revealed aerial chases inside the `perched` bucket inflates BirdNET from `0.618` (`p = 0.182`) to `0.711` (`p = 0.050`). Once genuinely stationary hawks are isolated, BirdNET is non-significant (`0.618`) and Perch 2.0 sits at **`0.504`**.

### 3. Secondary 2 — Within-Hawk Perched vs. Flying in audio-only archive checklists

| Archive subset & representation | `n` (`perched / flying`) | Recordists | ROC-AUC | Raw `perm_p` | Holm `p` | Density null AUC |
|---|---:|---:|---:|---:|---:|---:|
| **Strict zero-raptor, BirdNET** | **23 (`12 / 11`)** | 22 | **0.8106** | **0.0299** | 0.179 | **0.5000** |
| **Strict zero-raptor, Perch 2.0** | **23 (`12 / 11`)** | 22 | **0.9015** | **0.0125** | — | **0.5000** |
| Non-strict pure-crow, BirdNET | 37 (`14 / 23`) | 32 | **0.7360** | 0.0499 | 0.250 | 0.4907 |
| Non-strict pure-crow, Perch 2.0 | 37 (`14 / 23`) | 32 | 0.6708 | 0.0973 | — | 0.4907 |

In `0103` (before sibling checklist coding cleaned up the `unknown` and `mixed` hawks), archive within-hawk perched vs. flying had been `0.625` (`p = 0.32`, `8 vs. 10`). With sibling checklist postures resolved, **strict audio-only archive hawk posture rises to `0.811` (BirdNET, `p = 0.030`) and `0.902` (Perch 2.0, `p = 0.0125`) against an exact `0.500` density null** — reproducing `0104`/`0112`'s video result (`0.857` / `0.848`) on an entirely separate collection of audio-only Macaulay checklists, though small (`n = 23`) and exploratory/secondary after family-wise Holm adjustment over six tests.

### 4. Secondary 3 — Pooled Archive (`0116`) + Video (`0104`) Strict Perched Owl vs. Perched Hawk (`n = 82`: `55` owl, `27` hawk, `80` independent groups)

With dataset domain (`archive` vs. `video`) regressed out inside each training fold and permutations restricted within domain:

| Representation (`55` perched owl vs. `27` perched hawk, `80` groups) | ROC-AUC | Within-domain `perm_p` | Family Holm `p` |
|---|---:|---:|---:|
| **BirdNET (1024d)** | **0.6613** | 0.0499 | **0.2495** (null) |
| **Perch 2.0 (1536d)** | **0.5933** | 0.1771 | **0.4563** (null) |
| **CrowGPT block 4** | **0.6478** | 0.0424 | — |

*(Note: crowd size is still uncontrolled inside those `55` perched-owl vs. `27` perched-hawk recordings — stationary owls gather larger, denser mobs than stationary hawks, as `0104` and `0107` documented.)*

## What it changed

- **Macaulay's perched-hawk ceiling is now known:** Even after reading every sibling checklist via the eBird API, strict zero-raptor Macaulay recordings hold only **12 purely perched hawks** (because 22 checklists revealed vocalizing raptors and 2 "perched" hawks had actually flushed). No further text mining of this archive can reach 50 perched hawks.
- **Audio-only archive checklists point the same way as `0104`'s videos:** Cleaning hawk posture via sibling checklists lifts strict archive within-hawk perched vs. flying to `0.811` (BirdNET) / `0.902` (Perch) while leaving strict perched owl vs. perched hawk at `0.618` / `0.504`.
- **Saved `checklist_posture_labels.json`** (257 audited posture + `pred_vocal_checklist` flags), tightening strictness for `0117` and any future archive experiment.
