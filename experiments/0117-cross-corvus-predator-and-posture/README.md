# 0117 — Do predator and posture signals conserve across *Corvus* species once geography is removed?

**2026-11-22** · CPU (BirdNET) + GPU (Perch 2.0) · **answer: mixed, and pointing to posture/substrate rather than predator names — Eurasian → American Crow owl-vs-hawk zero-shot is null (0.491 BirdNET, 0.523 Perch; Eurasian owls rare at n = 4), and cross-*Corvus* strict perched owl vs. perched hawk is null in both backbones (22 vs. 16: 0.565 BirdNET, 0.565 Perch). Species-deconfounded mammal scold vs. avian raptor passes (0.873 BirdNET, Holm p = 0.0075; 0.876 Perch; 0.907 pure-recordist vs. 0.508 null; 0.919 within one Berlin recordist), and Eurasian *Corvus* hawk posture transfers zero-shot to North American `0104` hawk videos at 0.854 BirdNET (p = 0.00003)**

> **Pre-registration (written and committed in `437b51c` before reading/coding non-American-Crow remarks; blind labels frozen in `09146d4` before scanning audio).**

## The question

Every clean semantic test from `0103` to `0116` restricted itself to **American Crow**, leaving **8,908** downloaded Xeno-canto and Macaulay recordings (`6,316` with non-empty notes) across six other *Corvus* species (`hooded-crow`, `common-raven`, `carrion-crow`, `eurasian-jackdaw`, `rook`, `large-billed-crow`) unused in `corvid.db`. In `0102` (Section 4), naive cross-species pooling of mammal scolds vs. avian raptors hit `0.869` BirdNET AUC but failed its control because **metadata alone scored `0.799`** (European crows dominated mammal scolds while American Crows dominated raptor mobs).

This experiment removes geography/species leakage by construction via **(1) zero-shot Eurasian *Corvus* → American Crow transfer** (where 100% of test clips are one species on one continent) and **(2) within-fold species z-scoring + species one-hot orthogonalization** paired with **within-species** recordist permutations.

## Pre-declared protocol

1. **Blind remark coding (`09146d4`):** Keyword screening across all 8,908 downloaded non-American *Corvus* archive rows returned **454 candidates**, each blind-coded strictly from remark text into `owl_mobbing`, `hawk_mobbing`, `mammal_scold`, `human_disturbance`, or `none`, plus `witnessed`, `posture` (`perched, flying, mixed, unknown`), and `pred_vocal`. **160** recordings were coded as witnessed interactions (`labels.json`).
2. **Pure-corvid BirdNET & Perch 2.0 extraction:** Scanned `187/188` witnessed recordings (including `0102`'s witnessed American Crow `mammal_scold` / `human_disturbance` rows for uniform windowing) with BirdNET (`min_conf=0.05`) and embedded **2,364** corvid spans with Perch 2.0 (`perch_v2`, 1536d). Pure-corvid strict rule: corvid `>= 0.25`, `non_corvid < 0.05` in window, `pred_vocal == False` (plus `pred_vocal_checklist == False` from `0116` on American Crow), and recording-wide `max_raptor_conf < 0.05`.

---

## Results

Run once (`results.json`), followed by a post-hoc recordist-concentration audit on Primary B documented below.

### Inventory of strict pure-corvid non-American *Corvus* recordings (`n = 75` strict of `127` usable pure)

- **By species & context (strict):** `hooded-crow` (`18 mammal_scold, 13 hawk_mobbing, 3 human_disturbance`), `carrion-crow` (`9 hawk_mobbing, 8 mammal_scold, 1 owl_mobbing, 1 human_disturbance`), `common-raven` (`11 hawk_mobbing, 3 owl_mobbing, 1 human_disturbance`), `eurasian-jackdaw` (`3 hawk_mobbing, 1 human_disturbance`), `rook` (`2 hawk_mobbing, 1 human_disturbance`), `large-billed-crow` (`1 human_disturbance`).
- **Eurasian raptor posture skew (`non_amecro` strict):** Hawks are overwhelmingly flying (`18 flying, 4 perched, 2 mixed, 14 unknown`), while silent owls are rare in European archives (`3 perched, 1 unknown`; several Long-eared Owl mobs were excluded by `pred_vocal = true`).

### Co-primary results (family of 3, Holm-adjusted)

| Co-primary test | Scope (`pos / neg`) | BirdNET AUC | BirdNET `p` (Holm `p`) | Perch 2.0 AUC (`p`) | Deconfounded Null AUC | Verdict |
|---|---|---:|---:|---:|---:|---|
| **Primary A:** Zero-shot Eurasian *Corvus* → American Crow (`owl` vs. `hawk`, strict) | Train `4 / 38` → Test `70 / 53` | **0.4914** (`0.385–0.605`) | `0.872` (**`0.872`**) | **0.5229** (`0.666`) | — (single test species) | **NULL** (train `< 10` owls) |
| **Primary B:** Species-deconfounded Mammal Scold vs. Avian Raptor (strict, all *Corvus*) | `32 / 165` (`140` groups, 6 spp.) | **0.8729** | `0.0025` (**`0.0075`**) | **0.8759** (`0.0050`) | `0.6777` (raw meta `0.817`) | **PASSES** *(see audit below)* |
| **Primary C:** Cross-*Corvus* strict Perched Owl vs. Perched Hawk | `22 / 16` (`36` groups, 4 spp.) | **0.5653** | `0.299` (**`0.599`**) | **0.5653** (`0.289`) | `0.4886` (raw meta `0.580`) | **NULL** (both `>= 15`!) |

### Post-hoc audit of Primary B (`0.873` mammal scold vs. avian raptor) — why it passed, and two caveats

Inspecting recordist identities inside the 32 strict `mammal_scold` rows revealed that **one Berlin recordist (Johannes Worona) contributed 23 of the 32 mammal scolds** (`18/18` in Hooded Crow and `5/8` in Carrion Crow, plus `7/13` Hooded Crow raptor mobs), and `eval.py` had prefixed group keys by species (`slug:recordist`), letting his Hooded Crow and Carrion Crow files sit in different folds (which also caused the residualized metadata null to read `0.678` instead of `0.50`). Four post-hoc checks isolate what is real and what is recordist concentration:

1. **Grouping strictly by `recordist` across all species (`134` recordists, no `slug:` prefix):** The species-deconfounded density/metadata null drops to **`0.5083` (exact chance)**, and **BirdNET mammal-vs-raptor rises to `0.9068` (`perm_p = 0.005`)**. So cross-species recordist sharing did *not* inflate `0.873`; fixing it sharpened both the score and the null.
2. **Within Johannes Worona alone (`23` mammal scolds vs. `7` raptor mobs, 5-fold CV — same recordist, same Berlin urban parks, same microphone family):** BirdNET scores **`0.9193` AUC**. Within a single observer's park recordings, crows scolding foxes/dogs/cats on the ground sound markedly different from crows mobbing kestrels/buzzards.
3. **Excluding Johannes Worona completely (`9` mammal scolds from 9 independent recordists — 6 American Crow, 3 Carrion Crow — vs. `158` raptor mobs across 124 recordists):** Species-deconfounded BirdNET drops to **`0.7314`** (`perm_p = 0.0498`, deconfounded metadata null `0.608`).
4. **Zero-shot Eurasian *Corvus* (`26` mammal vs. `23` raptor) → North American American Crow (`6` mammal vs. `123` raptor):** BirdNET **`0.664`** (`95% CI: 0.463–0.849`, `mw_p = 0.182`), Perch **`0.627`** (`mw_p = 0.304`) — positive direction, underpowered at `n = 6` American Crow mammal clips.

**Ecological caveat on Primary B:** Terrestrial mammals (`fox, dog, cat, raccoon`) are **stationary/walking on the ground** while the crows scold from perches above, whereas Eurasian archive `hawk_mobbing` is **82% flying chases (`18:4` flying:perched)**. So `mammal_scold` vs. `avian_raptor` is entangled with **ground-perched scolding vs. aerial pursuit** — the same behavioral/postural contrast seen inside hawks, not proof of a taxonomic word for "mammal".

### Secondary 2 — Cross-*Corvus* Hawk Posture (`perched` vs. `flying`) & Zero-Shot Continental Transfer

| Test | Scope | BirdNET AUC (`p`) | Perch 2.0 AUC (`p`) | Deconfounded Null AUC |
|---|---|---:|---:|---:|
| All-*Corvus* strict archive within-hawk `perched` vs. `flying` | `16` perched / `29` flying (`41` groups, 6 spp.) | **0.7155** (`perm_p = 0.0274`) | — | `0.3556` |
| **Zero-shot Eurasian *Corvus* archive hawk posture → North American `0104` hawk videos** | Train `5 / 33` (Eurasia) → Test `27 / 21` (`0104` NA video) | **0.8536** (`95% CI: 0.729–0.948`, **`mw_p = 0.00003`**) | **0.6631** (`95% CI: 0.496–0.815`, `mw_p = 0.056`) | — (single target set) |

Even with only `5` perched vs. `33` flying Eurasian *Corvus* training clips, a BirdNET linear probe trained purely on European archive audio separates North American `0104` perched vs. flying hawk videos at **`0.854` AUC** zero-shot.

## What it changed

- **Cross-*Corvus* perched owl vs. perched hawk clears the `15`-per-class floor (`22` vs. `16`) and is null in both backbones (`0.565` BirdNET, `0.565` Perch).** Adding Eurasian *Corvus* perched raptors (including controlled Eagle-Owl and Goshawk dummy presentations) moves the needle toward `0.50`, not away from it.
- **Posture/substrate transfers across species and continents; owl-vs-hawk identity does not.** Eurasian *Corvus* hawk posture (`perched` vs. `flying`) transfers zero-shot to American Crow video clips (`0.854` BirdNET), while Eurasian owl-vs-hawk transfers at `0.491`.
- **Mammal scold vs. avian raptor separates strongly after species deconfounding (`0.873` / `0.907`, `0.919` within one Berlin recordist),** providing a promising ground-vs.-aerial threat axis — but it is carried heavily by one European recordist (`23/32` mammal clips) and confounded with ground-scolding vs. aerial-chase behavior until tested against **perched** raptors on multi-observer American Crow data.
