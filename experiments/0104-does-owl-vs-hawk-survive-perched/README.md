# 0104 — Does owl vs. hawk mobbing survive when both predators are perched?

> **Pre-registration (written 2026-11-21, before any new clip was searched, fetched, labelled or scored).**
> Everything in "Pre-declared protocol" was fixed first. Anything reported that is not named there as primary is labelled **exploratory**.

## Question

0102 found that American Crow recordings made while mobbing an owl separate from recordings made while mobbing a hawk (0.769 ROC-AUC, strict zero-raptor audio). 0103 showed the archive cannot say whether that is *predator* or *posture*: where recordists' remarks state it, owls are perched 16:2 and hawks are flying 18:12, and only 28 strict archive clips are explicitly perched (perched-only test null at n = 20).

Remarks rarely state posture. Pictures do. This experiment builds a set of public video clips of crows mobbing a raptor, reads the predator's posture from several frames of each clip, and asks one thing:

**With the predator perched in both classes, do crow recordings still separate owl from hawk?**

## Pre-declared protocol

### Clip set

- **Source:** public video clips of crows mobbing a raptor. The pilot set already fetched for the 0103 video study is reused; new candidates come from **one fixed round** of text searches (each predator — Great Horned Owl, Barred Owl, generic owl, Red-tailed Hawk, Cooper's Hawk, Red-shouldered Hawk, generic hawk, Bald Eagle — crossed with a fixed list of mobbing phrasings, perched and flying wording both, 40 results per query).
- **Title filter (before fetch):** title must mention a crow word and a predator word; duration 8–900 s. Duplicates of the pilot and of each other are dropped by clip id.
- **North America filter:** a clip is excluded, with the reason recorded, when its title, description or channel indicates another continent, or when the predator named or seen is not a North American species. The crow species is **not** verified per clip and cannot be; BirdNET's American/Northwestern Crow detection at >= 0.25 is the only acoustic gate.
- **Audio:** first 150 s of each clip, as in the pilot.
- **Usable-audio gate (applied before labelling, not a score):** a clip is labelled only if it has at least one *pure-crow* window (below). Clips with no usable crow audio are dropped unlabelled.

### Visual labels (blind)

- A contact sheet of **5 evenly spaced frames** (10 %, 30 %, 50 %, 70 %, 90 % of the fetched span) per clip.
- Labels: `predator_seen` (great_horned_owl, barred_owl, other_owl, red_tailed_hawk, coopers_hawk, red_shouldered_hawk, other_hawk, bald_eagle, other, not_visible), `predator_state` (perched, flying, mixed, on_ground, not_visible), `habitat`, `crow_count`, `clean_wildlife` (false for compilations, narrated edits, music beds, captive or rehab birds, decoys, cartoons, non-North-American scenes).
- Labelled from the frames and title only, **blind to every audio feature and model output**. The labels file is written and frozen before any classifier is run.
- `perched` means the predator is seen and is perched in every frame where it is visible. Any frame with the predator in flight makes the clip `mixed` (or `flying` if never perched).

### Masking (identical to 0103)

- BirdNET, `min_conf = 0.05`, 3 s windows. A **pure-crow window** has American/Northwestern Crow >= 0.25 and **no other species** detected at >= 0.05.
- **Strict set:** additionally, no raptor (0102's `RAPTOR_TERMS`) detected at >= 0.05 anywhere in the clip.

### Primary test

- **Subset:** `clean_wildlife`, North America, predator visually confirmed, `predator_state == perched`, strict set, >= 1 pure-crow window. Classes: **owl** (great_horned_owl, barred_owl, other_owl) vs. **hawk** (red_tailed_hawk, coopers_hawk, red_shouldered_hawk, other_hawk). Bald Eagle is a separate cell and is not in the primary test.
- **At most 2 clips per channel per class**, chosen by sorted clip id (not by any audio property).
- **Feature set:** recording-level mean BirdNET embedding (1024-d) over pure-crow windows.
- **Model and metric:** `StandardScaler` + `LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced")`, **5-fold `StratifiedGroupKFold` grouped by channel, ROC-AUC** on out-of-fold probabilities.
- **Significance:** 400-shuffle permutation test, labels shuffled across channels, same folds procedure; `p = (hits + 1) / 401`.
- **Null model:** the same pipeline (`C = 0.5`) on `duration_s`, `pure_crow_frac`, `n_pure_crow_windows` only.
- **Headline:** this one number, on the strict masked set. Never the best arm.

### Sample-size target and stopping rule

- **Target:** >= 50 clips per class in the primary subset.
- **Stopping rule:** one search round with the fixed query list; at most 800 new candidates fetched; no second round, no relaxation of any filter to reach the target. If a class ends below 50 the result is reported as **underpowered at the achieved n**; below 15 in either class the primary number is reported but declared uninterpretable.

### Exploratory (labelled as such wherever reported)

1. The primary test on the non-strict set (raptor may be audible) and without the per-channel cap.
2. Caw-level `caw_acoustic_44d` (0103's segmentation and features, unchanged), inverse-recording-weighted per-caw ROC-AUC, same folds.
3. Perched vs. flying **within hawk** (posture alone, predator held fixed), and perched hawk vs. perched Bald Eagle.
4. Zero-shot transfer: 0102's archive owl-vs-hawk model (BirdNET mean, strict American Crow archive clips) scored on these clips without refitting.
5. Density covariates per cell (pure-crow fraction, duty cycle).

---

## Results (2026-11-21)

Everything above this line was written before any clip was labelled or scored and has not been edited.

### What was collected

| stage | clips |
|---|---|
| search results, one round | 3840 raw |
| new candidates after the pilot/duplicate/title/duration filters | 551 |
| audio fetched | 501 (50 no longer available) |
| manifest with the pilot's clips re-used | 657 |
| usable audio (>= 1 pure-crow window) | 315 |
| frames fetched and labelled blind | 310 |
| excluded: not clean wildlife | 20 |
| excluded: not North America | 2 |
| excluded: predator never visible in the five frames, or a raptor that could not be put in a class | 120 |
| **predator confirmed, clean, North America** | **168** |

Cells of those 168 (all / strict):

| | perched | flying | mixed | on ground |
|---|---|---|---|---|
| owl | 68 / 37 | 0 | 0 | 3 / 1 |
| hawk | 27 / 15 | 21 / 16 | 9 / 6 | 2 / 0 |
| Bald Eagle | 25 / 6 | 4 / 1 | 3 / 2 | 6 / 3 |

The labels were frozen in `labels.json` (sha256 `ad7378c0…`) before `eval.py` was run for the first time, and `eval.py` was run once.

### Primary result: underpowered, and null at the n achieved

**Perched owl vs. perched hawk, strict masked set, BirdNET mean embedding on pure-crow windows: ROC-AUC 0.539, permutation p = 0.40 (shuffle mean 0.503). n = 36 owl, 15 hawk, 50 channels.**

Both classes are below the target of 50, so by the stopping rule this is reported as **underpowered at the achieved n**. The hawk class sits exactly on the floor of 15 below which the number was declared uninterpretable in advance. The density null on the same clips scores 0.522.

Read plainly: with the predator sitting still in both classes and no raptor audible, this set shows no owl-versus-hawk difference in the crows' calls — and it is too small to rule one out. With 15 clips in the smaller class the test could only have detected a large effect. It is a failure to find, not evidence of absence.

### Exploratory (none of these is the result)

| test | n | AUC | p | density null |
|---|---|---|---|---|
| perched owl vs. perched hawk, non-strict (raptor may be audible) | 67 / 27 | 0.642 | 0.045 (perm) | **0.666** |
| same as primary without the channel cap | 37 / 15 | 0.609 | 0.20 (perm) | — |
| caw-level 44-d, strict | 1039 caws, 50 recordings | 0.429 | — | — |
| caw-level 44-d, non-strict | 2095 caws, 93 recordings | 0.472 | — | — |
| **within hawk: perched vs. flying**, non-strict | 27 / 21 | **0.857** | 0.0025 (perm) | 0.609 |
| perched hawk vs. perched Bald Eagle, non-strict | 27 / 25 | 0.760 | 0.005 (perm) | — |
| 0102 archive model, zero-shot, perched owl vs. perched hawk, strict | 36 / 15 | 0.659 | 0.077 (Mann-Whitney) | — |
| 0102 archive model, zero-shot, perched owl vs. perched hawk, non-strict | 67 / 27 | 0.674 | 0.009 | — |
| 0102 archive model, zero-shot, perched owl vs. **flying** hawk, non-strict | 67 / 21 | 0.787 | 0.0001 | — |
| 0102 archive model, zero-shot, perched hawk vs. flying hawk, non-strict | 27 / 21 | 0.598 | 0.25 | — |

What these suggest, with the weight an exploratory table deserves:

- **Posture is the larger signal here.** Holding the predator fixed at hawk, the embedding separates perched from flying at 0.857, well above what clip length and crow density give on the same clips (0.609). Nothing in the owl-versus-hawk rows is that strong.
- **The non-strict owl-versus-hawk number is not above its own null.** 0.642 for the embedding against 0.666 for three density covariates: owl clips are longer and denser (median pure-crow fraction 0.55 vs. 0.27, 12 pure windows vs. 6), and that is enough to produce the score.
- **The archive model transfers a little, and most of what transfers follows posture.** Its owl-probability is higher on perched-owl clips than on perched-hawk clips (0.66–0.67), and the gap widens to 0.79 when the hawks are flying. It does not separate perched hawks from flying hawks (0.60), so it is not purely a posture detector either. The strict row does not reach 0.05.
- **Caw-level acoustic features carry nothing** in either set (below 0.5).
- Perched hawk vs. perched Bald Eagle separates at 0.76, with no density null computed for it and only 6 strict eagle clips, so it is unexplained rather than interesting.

### Caveats that bound all of it

- **Crow species is not verified.** The North America filter rests on title, description and channel text; 81 re-used pilot clips have no description at all, so for them it rests on the title. Fish Crows and Northwestern-range birds cannot be told apart from American Crows by this procedure, and BirdNET's label is the only acoustic check.
- **Five frames is a thin view of a clip.** "Perched" means perched in every frame where the predator was visible, not for the whole recording; a bird that flew between samples is labelled perched. 120 clips were dropped because no raptor was identifiable in five frames, which selects for close, steady footage — and owls are filmed close and still far more often than hawks.
- **Species within class is uneven.** Owls are mostly Great Horned (48 of 72 labelled owls); 28 of 66 hawks could only be called `other_hawk`. Several labels are marked low confidence in the `note` field and were kept, not dropped, since dropping them after seeing which way they fall would be a post-hoc choice.
- One labeller, one pass, no second rater.

### Deviations from the pre-registration

- Titles naming two predator types were dropped at the search stage (17 clips). This was done before any audio was fetched, but it is not in the text above.
- 5 clips with usable audio had no retrievable frames and could not be labelled.
- 3 pairs of clips turned out to show the same event under different uploads. One copy was marked not-clean; the other two pairs fell outside the primary cells (both unlabelled, and both Bald Eagle).
- The machine crashed during the audio fetch; 6 truncated files were discarded and re-fetched. Nothing downstream had run.

## What it changed

- **The owl-versus-hawk claim from 0102 is not supported once posture is held fixed, and is not refuted either.** The pre-registered test came back at chance on 36 vs. 15 clips. Nothing downstream should treat "crows call differently at owls than at hawks" as established; the honest status is "confounded with posture in every dataset so far, and the one deconfounded test was too small".
- **Posture moves ahead of predator type as the thing to test next.** Perched-versus-flying within hawk was the strongest and least density-explained contrast in the experiment. It is exploratory and needs its own pre-registered run, but it is where the evidence points.
- **Public video clips will not reach 50 perched hawks at this yield.** 657 clips gave 15 strict perched hawks: about 2%. A properly powered version needs a different source of perched-hawk mobbing recordings — not a second search round of the same kind.
- **Any future non-strict or unmasked owl-versus-hawk number must be shown beside its density null.** Here the null beat the embedding.
