# 0068 — does the long window buy range, and did the sitting measure polish?

**2026-08-11, predictions before results** · BirdNET embedding coverage, no
ears · **answer: no — the polish-vs-range geometry did not appear, and the
listening pool is not convicted**

## The question

0067 ended in a contradiction with a name: the gate says the 6 s window
taught real structure (4.13 units/bout, rhythm within 30 ms of real), the
48-trial sitting says the ear prefers the 3 s twin (0.441, six −2s), and
Ben's own read is *"long context holds more call diversity which might be
going in the right direction — short context makes really clean bouts...
long context has a defect but I think it is the future."*

The hypothesis this measures: **pairwise sittings structurally reward the
conservative arm.** A clean stereotyped bout beats an adventurous clip that
reaches for a rarer call and half-lands, every single trial — so a model
that covers more of real crow space at some cost in per-clip polish loses a
preference test *even when it is the better generator by the project's own
goal*. If that is what happened, the "ghost crow" is what a half-learned
call sounds like, and the listening pool — final judge since 0038 — has hit
a question it cannot answer.

This is checkable without ears, because polish and range make opposite
predictions about embedding geometry. Range is not dispersion: a model can
spread out into non-crow noise. Range is **coverage — landing draws in the
regions real crows actually occupy.**

## Design

A few hundred draws from each arm (model-longctx at max_frames 460,
model-units at 230 — trained by `crowgpt/tools/units_overnight.sh` — both
through the finetuned decoder, ≥ 1.0 s per 0044),
plus real bouts from bouts-6s' test split, all through BirdNET's
`embed_indexed` (the wrapper that keeps row indices — `embed()` silently
drops clips BirdNET finds no segment in).

The real set splits in half; the 95th-percentile nearest-neighbour distance
from held half to reference half is the **crow-space radius** — the typical
distance between a real bout and its nearest real neighbour from another
recording. Then, per arm, with draw counts equalised:

- **dispersion** — 0065's mean pairwise cosine distance. Variety, crow or not.
- **in-space share** (precision) — fraction of draws within the radius of
  some real bout. Polish lives here.
- **coverage** (recall) — fraction of real bouts with some draw within the
  radius. Range lives here. Bootstrap CI on the arms' difference.
- **exclusive coverage** — real bouts one arm reaches and the other does not.
- **coverage by source** — the real test bouts join back to their corpus
  source (0065's stem-parsing join), so if longctx's extra reach exists we
  see *where* it is: the archive #3 / soundscape-archive novel regions, or just more of
  the curated core.

Control: the held half's own coverage of the reference half is the ceiling
(~0.95 by construction of the radius).

## Predictions (written before running)

**Polish-vs-range says:** the twin wins in-space share (clean stereotyped
bouts land inside real regions — I'd guess ~0.85 vs ~0.70), longctx wins
coverage (my guess: ~0.45 vs ~0.30, CI-clear) and dispersion, and longctx's
exclusive coverage tilts toward the novel sources — the diversity 0065
proved arrived, finally being cashed. The ghosts are the price of reaching:
draws that fall *outside* the radius near thinly-learned regions.

**The null says:** coverage comes out equal or twin-favoured — longctx's
extra dispersion is spent outside crow space entirely (dispersion without
coverage), the ghost is plain incoherence rather than a half-landed reach,
and the sitting was right on the merits, not structurally biased.

**Decision rule:** coverage is the verdict cell. If longctx covers CI-clearly
more real regions, the sitting measured polish while the goal is range, and
this experiment's job extends to proposing what instrument replaces or
supplements pairwise preference — plus whether the 9–12 s rung (explicitly
not taken in 0067) is now worth taking. If coverage ties or reverses, the
pool system stands vindicated, longctx rests, and "ghost crow" goes back to
the probe queue as a coherence defect.

## Caveats

bouts-6s' test split is grouped within that store, but the 3 s twin trained
on a different extraction (bouts), so some test *recordings* here may appear
in the twin's training set. That asymmetry favours the twin on coverage —
so it cannot manufacture the predicted longctx win, only mask it; a longctx
coverage win survives the caveat, a twin win doesn't settle much.

## Result — the two arms are the same animal in texture space

253 draws per arm after equalisation, 298 real test bouts:

| | dispersion | in-space | coverage |
|---|---|---|---|
| real (ceiling) | 0.2625 | — | 0.954 |
| model-longctx | 0.2818 | 0.858 | 0.936 |
| model-units | 0.2860 | 0.842 | 0.940 |

Coverage difference −0.003, CI [−0.020, 0.013]. Exclusive coverage 3 vs 4
bouts out of 298. And the tie is not the radius saturating: `analyse.py`
walks the radius down to p25 and the arms track each other *and the
real-vs-real ceiling* at every quantile. The paired per-bout test — far more
power than any threshold — finds longctx nearer on 52.7% of real bouts,
p = 0.095. Both arms are also *at* real dispersion (slightly above it).

Neither predicted geometry fully happened. The twin did not out-polish
(in-space tied), longctx did not out-cover — and both cover curated crow
space about as well as real bouts cover each other, which is a finding in
itself about how far the texture side of this generator has come.

**The instrument is blind where the difference lives.** `birdnet_worker`
embeds a clip as the *mean over its 3-second segments* — a 6 s clip is a
texture mixture with the arrangement averaged away. So 0068 cleanly measured
texture range and cannot see sequence structure, which is exactly the
dimension 0067's gate showed moved (units, gaps, rhythm) and plausibly what
Ben's "more call diversity" means. The tie says: whatever differs between
these arms, it is not which spectral textures they can produce.

## The novel-region cell — a lean, not a reach

The test split turned out 88% macaulay — 0065's novel regions were barely in
the reference, so the range prediction's home cell went unmeasured by the
main run. `novel_reach.py` embeds novel-source bouts directly (both arms
trained on them; equal footing) and asks which arm's draws sit nearer,
paired per bout:

| source (0065 novelty) | n bouts | n recordings | longctx closer | p |
|---|---|---|---|---|
| community archive (12%) | 105 | 105 | 0.571 | 0.13 |
| soundscape archive (42%) | 72 | 12 | 0.611 | 0.022 |
| archive #3 (93%) | 42 | 5 | 0.714 | 0.019 |
| pooled | 219 | 122 | 0.612 | 0.00074 |

The gradient is exactly what range predicted — longctx's edge grows with the
source's novelty — but the honest unit is the recording, and there the
pooled lean is 0.582 at p = 0.098, resting on five archive #3 recordings.
The per-bout p is mostly pseudoreplication. What survives: a small,
directionally consistent lean of longctx toward real bouts (52.7% on the
curated core, 58.2% across novel recordings, both p ≈ 0.1, same sign;
mean edge ~0.004 against radii of 0.10–0.26). A lean the size of a rounding
error, pointed exactly where the hypothesis said — worth one line and
another look with more novel-source data, not a verdict.

## Verdict

**The strong hypothesis is refuted in the space where it could be measured.**
Longctx does not cover texture regions the twin misses, so the sitting was
not choosing polish over demonstrable range — the pool system keeps its seat
as final judge, and the "significant methodological finding" this experiment
went looking for is not licensed. The 0.441 stands as a real ear-level
judgement about something embeddings cannot see: coherence over 6 seconds,
the ghost.

If the arms differ, they differ in *arrangement* — where the 0067 gate
already scored longctx ahead and where no embedding instrument on hand can
look, because the embedder averages 3 s segments. The range question is not
answered no; it is moved to a space where the only current instruments are
the segmenter statistics and Ben's ear.

## What it changed

- **The 9–12 s rung stays untaken**, now with two grounds: the ear declined
  at 6 s (0067) and the window buys no texture range to offset it (this).
- **The next lever is unchanged and sharpened: name the ghost.** The longctx
  case now rests entirely on structure, and the −2 tail is what cancels it.
  0067's queued probes (per-burst harmonicity, attack transients, late-half
  embedding distance) are the path; this experiment adds that the failure is
  not a texture the twin lacks — per-segment embeddings of ghost clips vs
  their own clean siblings would be the discriminating version.
- **No new sitting instrument gets built.** The case for replacing pairwise
  preference collapsed with the coverage tie. What 0067's sittings actually
  lacked — the why behind ties and −2s — is already addressed the cheap way:
  the /listen page now prompts for defect tags on 0 and ±2 grades, and
  "ghost" is in the vocabulary.
- The novel-reach lean earns a **FUTURE.txt entry, not an experiment**:
  revisit when the corpus tooling brings more archive-#3-like material
  (5 recordings cannot carry a claim), or when a structure-aware embedding
  exists to redo coverage in the space that matters.
