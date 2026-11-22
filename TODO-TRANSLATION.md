# CrowGPT — Semantic Translation TODO

Focused task list for Problem 2 (mapping crow calls to witnessed meanings), split out from the larger `TODO.txt` on 2026-11-21.

## Completed (2026-11-21)
- [x] **Experiment 0102 (`f9df3bc`, `55e0921`, `fb663bd`, README corrected):** Harvested 561–580 witnessed American Crow recordings (~18 hr) from Xeno-canto + Macaulay remarks; established recording-level 7-class semantic separability (**0.811 macro AUC**), strict zero-raptor recording-level owl vs. hawk (**0.769 AUC, `p = 0.005`**, metadata null `0.469`), and documented honestly why the first 4-class threat head (`0.757` macro AUC on 378 clips; verdict precision `owl 51/90`, `hawk 20/51`, `terrestrial 2/21`; Poe Family `0.683, p = 0.243` with `7/29` hawk false alarms) is **not ready to ship**.
- [x] **Reverted `analyzer/` integration (`94d5e81`):** Kept `analyzer/`, `fieldserver/`, `dashboard/`, and `promo/` clean until caw-level and posture-controlled evidence plus usable operating-point precision are established.
- [x] **Experiment 0103 (`experiments/0103-caw-level-and-posture-controls/`):** Pre-registered caw-level owl vs. hawk with strict all-non-crow BirdNET masking, blind posture coding across all 148 strict remarks, and a locked `2023-01-01` temporal holdout:
  - **Bystander masking cleared:** Masking every non-crow BirdNET detection (`>= 0.05`) left dev recording-level BirdNET nearly unchanged (`0.651 → 0.639`, density-matched `0.668, p = 0.040`) and held at `0.792` (`p = 0.005`) on the untouched `2023+` holdout.
  - **Caw-level mixed / not yet proven:** Dev CV (`date < 2023`, `n = 100`, 2,150 caws) was **null** (`0.516, p = 0.409` full; `0.597, p = 0.077` density-matched), whereas the untouched `2023+` modern-digital holdout (`n = 32`, 718 caws) scored **0.720** weighted per-caw (`0.843` rec-mean, `p = 0.001`; zero-overlap `0.721`).
  - **Posture confound confirmed & underpowered:** Posture-explicit archive remarks are 89% perched for owls (`16:2`) vs. 60% flying for hawks (`12:18`), with only `28` explicitly perched clips total (`n = 20` dev -> `0.490, p = 0.444` null; `n = 6` holdout -> `0.500` null).

## Next research steps (before any `analyzer/` or UI integration)
- [ ] **Resolve the posture confound at scale:** Collect a larger **modern-digital, explicitly perched** owl vs. perched hawk dataset (plus matched flying/terrestrial controls) so perched-only evaluation has real power (`n >= 50` per class), and fix train/serve region-length matching before revisiting any shipped head.
- [ ] **Audit `0102`'s 77 witnessed begging clips by ear** and fold clean spans into `pipelines/ingest/` to bolster the weak `begging` class in the shipped `calltype_clf` head.
- [ ] **Investigate the dev (<2023) vs. holdout (2023+) caw-level gap:** Check whether pre-2015 legacy tape audio / SNR filtering explains the dev fold variance (`0.355–0.610`) or whether 2023+ holdout was carried by its `7 flying / 2 perched` hawk posture skew.

## Later (recorded in `FUTURE.txt`)
- [ ] **Two-way semantic generation (Item 3):** Condition CrowGPT (Dual-AR `0101`) on verified semantic contexts once a high-precision, posture-controlled classifier exists.
- [ ] **Probe CrowGPT hidden states on 0102/0103 witnessed recordings (Item 4):** Benchmark `0101` Dual-AR intermediate activations against BirdNET and Perch 2.0 on the exact same strict pure-crow dev/holdout split.
