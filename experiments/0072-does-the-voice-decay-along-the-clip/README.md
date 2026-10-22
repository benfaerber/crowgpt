# 0072 — does the voice decay along the clip?

**2026-08-11, predictions before results** · positional periodicity, no
ears · **answer: no — and real bouts RISE, which no model reproduces**

## The question

Three threads point at the same untested axis — *position within the
clip*:

- Ben's dose-2 note: *"started good but robo. end is bad"* — the only
  note that ever located a defect in time.
- 0067's −2 post-mortem: "a 6 s clip must hold coherence twice as long,
  and when it fails it fails audibly" — asserted, never measured.
- 0069's mechanism: dust is the model playing it safe. If safety is what
  a context full of generic tokens conditions toward, dust should
  *accumulate* — each bland burst makes the next more likely — rather
  than strike uniformly.

The probe already exists (pitch strength, `lib/dustprobe.py`). This runs
it per burst, ordered in time, and asks whether generated voice fades
along the clip while real voice holds.

## Design

Per clip, per burst: pitch strength, indexed by burst ordinal and by
normalised position. The per-clip statistic is **late-minus-early Δ**
(mean pitch strength of the second half of bursts minus the first half,
clips with ≥2 bursts). Arms:

- real 6 s test bouts (control — the decay must be ~0 here or the
  feature, not the model, drifts with position)
- model-longctx at default T 1.0 / k 200
- model-longctx at the candidate T 1.1 / k 200 — same clips length, more
  commitment per 0069
- model-units, the 3 s twin — half the window, so per-second decay shows
  up half as large per clip if decay is a rate, equally if it is a mode

150 draws per generated arm (seeds 20000+), ~200 real, finetuned decoder
throughout (within-decoder comparisons only, per 0070's caveat).

## Predictions (written before running)

- **Real is flat:** |mean Δ| < 0.01.
- **Generated arms decay:** mean Δ ≤ −0.02, Wilcoxon-clear, and the decay
  is larger for longctx than for the 3 s twin *per clip* (more room to
  fall) but similar *per second* — decay is a rate, the accumulation
  story.
- **T 1.1 decays less than T 1.0** — more commitment resists the slide —
  which would hand the dust sitting a mechanistic reading before it is
  even graded.
- Named alternative: all arms flat, dust strikes uniformly → dust is a
  per-burst mode, not an accumulation; the "coherence over 6 s" story
  dies and the −2 tail needs another explanation; window length stops
  being suspect for the tail at all.

## Result — no decay anywhere, and a crescendo only the crows have

Per-clip late-minus-early Δ pitch strength:

| arm | n | mean Δ | declining share | Wilcoxon |
|---|---|---|---|---|
| longctx T 1.0 | 150 | −0.010 | 0.54 | 0.36 |
| longctx T 1.1 | 150 | +0.003 | 0.56 | 0.66 |
| units 3 s | 150 | −0.005 | 0.55 | 0.33 |
| **real 6 s** | 200 | **+0.018** | **0.445** | **0.039** |

**The named alternative wins:** generated voice is flat in time — no arm
decays, dust strikes per-burst rather than accumulating, and the
"coherence over 6 s" reading of 0067's −2 tail is dead. Window length is
off the hook for the tail entirely; the accumulation half of 0069's
playing-it-safe mechanism is refuted while its per-burst half stands.

**The unpredicted finding is the real row:** real bouts *brighten* as
they proceed — a within-clip rise (the paired statistic, immune to the
survivorship that inflates the by-ordinal table) that fits what a bout
is behaviourally: a session that builds. Every model is flat where the
crows crescendo. That is a new, cheap, measurable axis of the structure
gap, and unlike units-per-bout it is about *trajectory*, not count.

Supporting detail worth keeping: T 1.1's overall pitch strength (0.505
early) sits at real's level (0.509) where T 1.0 sits at 0.477 —
independent corroboration of 0069's dust ordering by a statistic the
grid never used.

## What it changed

- The −2 tail explanation space narrows again: not fading energy (0067's
  ghost probe), not texture the twin lacks (0068), not positional decay
  (this). What remains is per-burst: some caws are simply born dusty,
  which is what the dust sitting's per-clip notes can now confirm or kill.
- **The crescendo joins the structure instruments.** Next gate that
  compares arms on structure should report mean Δ alongside units and
  gaps — a model that learns bouts should eventually learn that they
  build. No new experiment needed; it is one line in the next gate.
- T 1.1's pitch-strength parity with real is one more reason the dust
  sitting's hot arm is the likely winner; the sitting still decides.
