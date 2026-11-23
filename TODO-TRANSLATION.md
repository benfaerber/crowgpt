# CrowGPT — Semantic Translation TODO

Focused task list for Problem 2 (mapping crow calls to witnessed meanings and behaviors), split out from `TODO.txt` on 2026-11-21 and updated through Experiment `0119` on 2026-11-22.

## Completed (2026-11-21 → 2026-11-22)

- [x] **Archive & corpus context benchmarks (`0102`, `0106`, `0109`–`0111`):**
  - Harvested witnessed Xeno-canto + Macaulay remarks (`0102`), built a per-window crow-count covariate (`0109`, `0.802` within call type; upgraded to `0.845` with CrowGPT Dual-AR block 4 in `0112`), verified out-of-archive context transfer (`0110`: `begging` `0.9996`, `roost` `0.776` [mostly crowd], `raptor_mobbing` `0.731`, `food` `0.650`, `flight` `0.634`), and measured ordinary-recording false alarms on the begging head (`0111`: `4.0%` winter, `21.2%` hand-labelled archive segments -> gated on a summer listening pool before shipping).
- [x] **Exhaustive tests of taxonomic predator nouns (`owl` vs. `hawk`) — consistently NULL once posture & crowd are controlled (`0103`, `0104`, `0107`, `0112`, `0115`–`0118`):**
  - Isolated single caws (`0103`, `0112`): null across 44 waveform features (`0.516`), BirdNET (`0.522`), Perch 2.0 (`0.546`), and CrowGPT Dual-AR (`0.430`).
  - Single-bird bout cadence & caw order (`0115`): null on strict owl vs. hawk (`0.353`, Holm `p = 1.0`), and scrambling caw order inside every bout leaves 5-context AUC unchanged (`0.581` real vs. `0.587` shuffled).
  - Posture-matched perched owl vs. perched hawk: null on `0104` video (`0.539` BirdNET, `0.569` Perch), `0116` sibling eBird checklists (`0.618` BirdNET, `0.504` Perch; pooled archive + video `0.661`, Holm `p = 0.250`), `0117` cross-*Corvus* pooling (`22 vs. 16`, `0.565` BirdNET / `0.565` Perch; Eurasian -> American Crow zero-shot `0.491`), and `0118` BirdMixIT-separated mob stems (`0.567` caw-level dev, `0.474` perched video).
- [x] **Positive discovery — threat posture & engagement (`perched/stationary` vs. `flying`) replicates across media, backbones, and continents (`0104`, `0112`, `0116`–`0118`):**
  - Within-hawk `perched` vs. `flying` scores `0.857` BirdNET / `0.848` Perch on `0104` video, rises to **`0.905`** after BirdMixIT stem separation (`0118`), replicates at **`0.811` BirdNET / `0.902` Perch** on audio-only Macaulay checklists (`0116`, density null `0.500`), and transfers **zero-shot at `0.854` AUC** from Eurasian *Corvus* audio to North American `0104` hawk videos (`0117`). Species-deconfounded terrestrial mammal scold vs. mostly-flying raptors scores `0.873–0.907` (`0117`).
- [x] **Single-bird graded prosody (`0113`) & generative scene bits (`0114`):**
  - Single-bird caws carry modest 5-context signal (`0.665` macro AUC, `0.775` BirdNET; caw duration longest in `begging`, shortest in `flight_contact`, faster/higher in `raptor_mobbing`), while `0114` showed naive context tokens in Dual-AR mostly spend bits on crowd and fine-stage channel timbre (`0.692` raw -> `0.572` crowd-removed).
- [x] **Time-locked call-consequence / pragmatics mining (`0119`):**
  - Tested across `5,161` deduplicated `24–300 s` American Crow recordings in `corvid.db`: single-bird recruitment (`0.549`), isolated terminal caws before `>= 15 s` live-mic silence (`0.490` BirdNET / `0.483` `caw_44d`, after uncovering `0.749` fixed-grid phase leakage in 3 s BirdNET windows), and Capture 104's parental begging-cessation hypothesis (`14.81%` stop rate after adult calls vs. `16.75%` after a plain 3 s silent pause; call acoustics `0.577` null) are all **null** in audio alone.

## Next high-leverage steps (before shipping new semantic UI)

- [ ] **Fresh, pre-registered confirmatory posture set (`FUTURE.txt`):** Both `0104` and Macaulay sibling checklists are now spent. Build an untouched confirmatory set for within-predator `perched` vs. `flying` (and `perched raptor` vs. `ground mammal`) via 24/7 public raptor perch/nest live streams, researcher taxidermy-mount WAV outreach (`phases/outreach.md`), or the roof-station camera (`phases/roof-station.md`).
- [ ] **Cash in BirdMixIT (`0118`) + explicit `none` class (`0036`) on `analyzer/` (`TODO.txt`):**
  - Test pretrained 22.05 kHz BirdMixIT (`+4.4 / +7.0 dB` 2-crow SI-SDRi) on `crow-tools`'s `crowCount >= 2` segments where `mob` AP currently collapses to `1.33×` chance.
  - Train and validate the 5-class American Crow head with an explicit `none` class (`0036` `garbage.npz`) so CawDex stops emitting `alarm call` (`p = 0.90`) on 97% of crow-free windows.
- [ ] **Two human-ear listening pools (`register_pool.py`, `FUTURE.txt`):**
  - Validate `0103`/`0113`'s single-bird caw segmenter against human caw counts so graded **caw duration & rate** can ship beside call type.
  - Grade `0111`'s summer `June–July` pool (`75` firings + `75` non-firings) to calibrate and unlock the recording-level `begging` detector.
