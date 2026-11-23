# GPU calendar

Who has the RTX 4070 Ti SUPER (16 GB), and until when.

One GPU, two claimants: Ben's interactive work and crowgpt's training runs. A
run that starts while the card is already spoken for does not fail cleanly — it
OOMs several hours in, or it quietly slows the thing it collided with. So the
booking goes here *before* the run starts, and an agent reads this file before
allocating anything.

**Convention.** Newest booking at the top. Give the end time, not a duration —
"until 19:00" survives being read three hours later in a way "4 hours" does not.
Strike a booking through when it ends rather than deleting it, so the next
person can see what the card has actually been doing.

**If you need the GPU and it is booked:** say so and wait, or ask. Do not size a
job to "probably fit alongside" — 0036 ran entirely on CPU for exactly this
reason and lost nothing by it.

---

## Booked

- **2026-11-22 21:14 → 2026-11-23 00:15 (America/Denver)** — **Experiments 0115–0118**: CPU for 0115–0116; Perch 2.0 embeddings on non-American *Corvus* windows (0117, ~2 GB VRAM with `TF_FORCE_GPU_ALLOW_GROWTH=true`) and BirdMixIT 4-stem separation on synthetic 2-crow mixtures + mob windows (0118, ~2–3 GB VRAM). Bushcrow; Ben authorized running alongside the active video render. Killable on request.

- ~~**2026-11-22 15:45 → 2026-11-22 23:00 (America/Denver)** — **Experiments 0112–0114**: EnCodec + CrowGPT Dual-AR 17M hidden-state extraction and Perch 2.0 embeddings over archive/0104/0110 crow windows and 0103 caws (a few GB), then ten short Dual-AR context fine-tunes for 0114 (~1–2 GB each). Whiskyjack; Ben asked for the three experiments. Killable on request.~~ Done 16:57; card released.

- ~~**2026-11-21 21:04 → 2026-11-21 21:10 (America/Denver)** — **Experiment 0102 crow-masked Perch 2.0 Poe Family check**: Perch 2.0 inference over BirdNET-detected crow windows only (~200 windows across 25 kept captures, ~2 GB VRAM, ~20 s). Pinyon. Killable on request.~~ Done 21:05; card released.

- ~~**2026-11-21 20:37 → 2026-11-21 20:55 (America/Denver)** — **Experiment 0102 Perch 2.0 threat-translation benchmark**: Perch 2.0 embedding extraction over ~375 strict witnessed American Crow archive recordings + 29 kept Poe Family captures + local eval clips (~2–3 GB VRAM, ~4 min). Pinyon. Killable on request.~~ Done 20:51; card released.

- ~~**2026-11-21 14:57 → 2026-11-21 15:47 (America/Denver)** — Chatterbox voice clone for the feature's scratch narration (a few GB, a few minutes), then the Blender EEVEE preview (960×540) of the feature film in `promo/video/`. Rook. Killable on request.~~ Done 15:46; card released.

- ~~**2026-11-21 13:28 → 2026-11-21 14:13 (America/Denver)** — Blender EEVEE re-render of the eight crow-vision shots in `~/Code/crowsim` at a slower pace, several Blender processes at once, a few GB of VRAM. Rook. Killable on request.~~ Finished 13:49. Card free.

- ~~**2026-11-21 12:25 → 2026-11-21 12:45 (America/Denver)** — **0101 listening pool `quality-0101`**: sampling 44 clips each from CrowGPT2 and 0101 Dual-AR `q4_crisp CFG 1.6` (~0.6 GB VRAM, ~3 min). Currawong; Ben requested step 1.~~ Done 12:30. Card free.

- ~~**2026-11-20 21:15 → 2026-11-21 00:15 (America/Denver)** — Blender Cycles (OptiX) render of the tall 1080×1920 explainer in `promo/video/`, about 3 GB of VRAM. Rook. Killable on request: it resumes from the frames already written.~~ Finished 23:24. Card free.

- ~~**2026-11-20 10:11 → +2 h (America/Denver)** — Blender Cycles (OptiX) render of the square 1080×1080 explainer in `promo/video/`, about 3 GB of VRAM. Rook. Killable on request: it resumes from the frames already written.~~ Finished 11:32. Card free.

- ~~**2026-11-20 07:28 → 2026-11-20 09:30 (America/Denver)** — **experiment 0101: recording-quality conditioning + CFG on Dual-AR 17M** (240k steps on `tokens-6s` with spliced acoustic quality tier + 15% CFG dropout, ~1.1 GB VRAM, ~95 min total). Currawong; Ben approved ("Lets do it").~~ Done 09:25. Card free.

- ~~**2026-11-19 23:27 → 2026-11-20 06:30 (America/Denver)** — **experiments 0099 (done 02:24) + 0100 (Dual-AR scaling: 17.3M @ 240k + ~40M d512/L8+D3 @ 120k + 0015 memorisation check + morning diagnostic page; ~1–3 GB VRAM)**. Currawong; Ben offered the GPU overnight ("Lets do A").~~ Done 05:34. Card free.

- ~~**2026-11-19 18:00 → 2026-11-19 21:00 (America/Denver)** — Blender Cycles (OptiX) render of the 1080p narrated explainer in `promo/video/`, about 3 GB of VRAM. Rook. Killable on request: it resumes from the frames already written.~~ Finished 20:13. Card free.

- ~~**2026-11-16 21:45 → 2026-11-17 00:30 (America/Denver)** — Blender Cycles (OptiX) render of the 1080p explainer in `promo/video/`, about 3 GB of VRAM. Rook. Killable on request: it resumes from the frames already written.~~ Finished 23:39. Card free.

- ~~**2026-11-16 20:00 → 2026-11-16 22:30 (America/Denver)** — Blender Cycles renders of the promo films in `promo/video/`. Rook.~~ Withdrawn 20:05: Jay's 0098 took the card under the booking below seconds before the render started, and the two collided. Renders are back on the CPU.

- ~~**2026-11-16 15:10 → 2026-11-16 23:00 (America/Denver)** — experiment 0097: a CrowGPT2-sized model (18.7M params) trained for 60k steps at two learning rates, the control for 0096 (~6 GB). Jay; Ben offered the card.~~ Done 20:50: 0097 and the 0098 trainer checks finished, card free.

- ~~**2026-11-16 12:30 → 2026-11-16 14:00 (America/Denver)** — 0096 listening pool: sampling ~250 clips from CrowGPT2 and the 60k candidate (a few GB). Jay.~~ Done 12:46, card free.

- ~~**2026-11-15 18:15 → 2026-11-16 09:00 (America/Denver)** — **0095 machine judge for the listening sittings**: Whisper/CLAP/codec embeddings of the pool clips (small), then a 4-bit audio-language model scoring every graded trial (~10 GB), then, if the night allows, the 0086 candidate trained past 30k. Jay; Ben made the GPU and CPU available overnight.~~ Done 2026-11-16 02:10: 0095 and 0096 both finished, card free.

- ~~**2026-11-13 19:30 → 2026-11-13 22:00 (America/Edmonton)** — PANNs sound-event pass over ~48 h of short clips (~4,800 files), well under 2 GB VRAM; BirdNET half is CPU. Treepie; Ben made the GPU available.~~ Finished early; PANNs ran on CPU in the end and never held the card. Released.

- ~~**2026-11-12 20:40 → 2026-11-12 21:30 (America/Edmonton)** — PANNs sound-event pass (speech/music/crow per second) over ~2 h of short clips, well under 2 GB VRAM. Treepie.~~ Finished; card free.

- ~~**2026-09-10 10:38 → 2026-09-10 20:38 (America/Edmonton)** — **0086 controlled CrowGPT3 learning-rate comparison**. Three sequential d512/L12 runs, true batch 8, fixed validation, checkpoint selection, generated gate and blinded listening pool. Chough; Ben explicitly made GPU available.~~ Completed successfully 2026-09-10 16:38; listening pool ready, GPU reservation released.

- ~~**2026-09-09 22:53 → 2026-09-10 09:00 (America/Edmonton)** — **0085 CrowGPT3 capacity candidate**, d512/L12, six-second corpus, effective batch 8, preflight → 30k training → matched validation. Chough; Ben authorized overnight GPU use.~~ Finished successfully 2026-09-10 00:15; card released. Candidate failed the instrument screen.

- ~~**2026-08-19 (Tue) → 06:00 next morning** — **"0080 — does the batch fix
  reach the incumbent?"**: model-longctx's exact recipe at true effective
  batch 32 (~4 h train + 30 m validation), doubling as 0079's deconfounding
  arm. Booked by Raven at Ben's ask for unattended work.~~ Finished; val went the wrong way, incumbent stands. Card free.

- ~~**2026-08-17 (Sun) 23:00 → 09:00 next morning** — **"0079 — does nine
  seconds buy more structure?"**: tokenize bouts-9s, VRAM preflight at block
  ~5500, train model-long9 at true effective batch 32 (~6 h), then the 0067
  structure instruments against a 9 s real reference. Booked by Raven; Ben
  asked for overnight work before bed.~~ Finished; ladder closed at 6 s. Card free.

- ~~**2026-08-17 (Sun) → 17:00** — **"0077 — does matching the calltype recipe
  close the gap?"**: the conditioned 6 s candidate at n_head 6 / 40k steps /
  true batch 32 (~5.5 h train + 40 m validation). Booked by Raven; Ben said
  "let's do 77" before work.~~ Finished early (~13:00, early stop at 18k). Card free.

- ~~**2026-08-16 (Sun) 01:00 → 09:00** — **"0075 — does the batch the recipe
  claimed matter?"**: model-longctx-ct retrained at true effective batch 32
  (--accumulate 4, ~4 h), then the 0074 validation harness on the result
  (~40 min). The parallel 9 s extraction is CPU-only and takes no card.
  Booked by Raven; Ben asked for overnight improvement before bed.~~
  Finished ~05:45: val 4.689 (was 4.781), b32 is the candidate. Card free.

- ~~**2026-08-16 (Sun) 00:30 → 04:00** — **"0075 — begging labels refit +
  retrain"** (relabel is CPU; the card carries a ~1 h train and the re-gate
  draws). Booked by Raven, approved by Ben.~~ Struck unused ~00:45: the
  begging post-mortem (0074 README addendum) measured all four fix
  hypotheses dead before the card was touched. Card free.

- ~~**2026-08-15 (Sat) 19:20 → 09:00 next morning** — night chain **"0074 —
  conditioned longctx retrain"** (label pass is CPU/TFLite ~25 min, then the
  card carries the ~2 h train plus smoke draws; booked wide so a stall is
  covered until the morning check). Booked by Claude, approved by Ben.~~
  Finished 23:5x same evening — train 58 m, validation and the serving-condition
  supplement included. Card free.

- ~~**2026-08-02 (Sun) 15:07 → 19:00** — training run **"0037 — A FLAT GENERATOR
  ON DAC-44"**. Booked by Ben. Assume the full card is in use; treat free VRAM
  reported by `nvidia-smi` as headroom that may vanish, not as available.~~

## Free

- Nothing else booked.

---

## Notes for agents

- `nvidia-smi --query-gpu=memory.used,memory.free --format=csv` reports the
  card's *current* state, which is not the same as its *committed* state. A run
  between two stages can look idle. This file is the authority; the card is not.
- Most of this project's analysis does not need the GPU at all. BirdNET is
  TFLite on CPU — birdnetlib sets `CUDA_VISIBLE_DEVICES=""` at import, so it
  could not use the card even if asked — and every shipped call-type head is an
  sklearn logistic regression. Experiment 0036 measured a learning curve, three
  embedding passes and a backbone comparison without touching the GPU.
- What genuinely needs it: crowgpt training and sampling, DAC/EnCodec
  tokenisation, and any future Voxaboxen or Perch work.
