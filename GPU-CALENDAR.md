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
