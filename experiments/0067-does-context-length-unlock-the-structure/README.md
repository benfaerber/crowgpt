# 0067 — does context length unlock the structure?

**2026-08-11, predictions before results** · overnight-plus build · **answer:
pending**

## The question

The surviving piece of Ben's 0064 hypothesis, and the pointer every recent
result converges on: the 3 s bout cap discards between-call structure at
extraction, so no amount of corpus (0064), diversity (0065 — it arrived),
or conditioning (0066 — a nudge) can teach what the training data never
contains. This doubles the window: bouts capped at 6 s, sequences ~3,600
codec tokens (fits the default 4,096 block), same recipe otherwise, units
token inherited.

## Predictions

- **Ben's, by extension:** with room for real sequences — call, answer,
  spacing — generated bouts gain the churn and rhythm of a session rather
  than a blip; 0024-family stats (units per bout, inter-burst timing) move
  toward real on the 6 s reference distribution.
- **The null shape:** longer clips of the same local texture — unit density
  flat relative to the 6 s real reference, timing structure absent — which
  would say the recipe's capacity, not its window, is binding, and point at
  model scale or architecture next.

## Build

Night chain under `crowgpt-night` (tools/night_0067.sh), emails Ben on any
failed step: 0065's fixed-join rerun first (cheap), then extract with
`CROWGPT_BOUT_MAX_SEC=6` to `bouts-6s` (~2 h), tokenize `--units --bouts`
to `tokens-6s`, train to `results/model-longctx` — ~2× step cost at double
sequence length, so this lands tomorrow evening, not morning.

## Gate

0024's instruments against the **6 s real distribution** (the reference
changes with the cap — comparing against 3 s real bouts would be a category
error): units per bout, single-share, and inter-burst gap statistics, drawn
from model-longctx vs model-units (the 3 s twin) vs 6 s real bouts. Ears
only if the numbers move.

## Result — the window matters: most of the structure gap closed

Against the 6 s REAL reference (which itself moved: 5.1 mean units, 6.5%
single, 4.16 gaps/clip, 0.267 s median gap):

| arm | mean units | single | gaps/clip | median gap |
|---|---|---|---|---|
| real 6 s | 5.10 | 0.065 | 4.16 | 0.267 s |
| **model-longctx** | **4.13** | 0.26 | **3.32** | **0.299 s** |
| model-units (3 s twin) | 3.29 | 0.19 | 2.45 | 0.288 s |

Ordering is clean and monotone: twin ≪ longctx < real. The long-context
model closes most of the twin's structure deficit — a full extra caw per
bout, an extra gap per clip, rhythm within 30 ms of real — but is not yet
AT parity (MW vs real p = 0.009, where the twin sits at p ≈ 0). Head-to-head
longctx vs twin is directional, unresolved at n = 100 (p = 0.19); the
meaningful contrast is the asymmetry of the two vs-real tests. Val loss
4.686 is logged, not compared — different corpus, different val set.

**Verdict: Ben's prediction wins on direction** — giving the model a window
that can contain sequences teaches it sequences; the null's "longer clips of
the same texture" is refuted by the gap-count and rhythm numbers. What it
changed: the 6 s corpus becomes the standing corpus candidate; the follow-up
ladder is window length (9–12 s) before capacity; and a sitting is warranted
for the first time since 0064 — structure moved, so ears can now hear
something the instruments already believe.

## The sitting — the ear declines to confirm the instruments

48 anchored trials, doses of 20: **P(longctx preferred) = 0.441 [0.29,
0.61]** — a statistical tie leaning against, with the graded margin at
−0.2 and the strong opinions asymmetric: six −2s against longctx, two +2s
for it. The 0044 length check clears the comparison (longer clip preferred
only 0.353 [0.22, 0.52] — if anything a headwind against the longer arm,
not a tailwind). Catches 6/8 real. Defect tags unused for a second
consecutive sitting.

So the full 0067 arc: **the window taught the model measurably real
structure (gate) that the ear does not yet hear as a better crow
(sitting)** — 0037's lesson recurring one level up: instruments moving
before sound does. The −2 tail suggests why: a 6 s clip must hold coherence
twice as long, and when it fails it fails audibly. The structure gain and
the coherence cost currently cancel.

**What it changed:** the 9–12 s ladder rung is NOT taken — a longer window
must first earn audibility at 6 s. The next question is the −2 tail:
re-listen those specific trials' clips (seeds in the pool spec) and name
what fails — that description, not another scaling step, decides between
capacity, sampling, and window as the binding constraint. The 6 s corpus
stays standing as a corpus (its REAL bouts and reference distributions are
better instruments regardless of which model wins).

## The tail listen — a new word, and a probe that missed

Ben on the six −2 clips: *"a new thing I can't describe. Not like a robot.
Like a ghost crow almost."* Not the robot/scratchy/modem family — those were
codec artifacts and they are gone. A genuinely new defect word.

First mechanistic guess — ghost caws are low-confidence continuations, so
late bursts should fade — **tested and mostly refuted** (`ghost_probe.py`):
late-minus-early peak is −0.2 dB in the failed clips against +1.2 dB in
their real anchors. Ghosts hold their volume. The failure lives somewhere
the current instruments don't measure — candidate next probes: per-burst
harmonicity/spectral shape, attack transients, or embedding distance of
late halves. Written down as the open question it is: **what is a ghost
crow made of?** The answer names the next lever; until then the longctx
arm rests and the 3 s twin remains the incumbent.

**Renamed 2026-08-11, during the second sitting:** Ben replaced "ghost"
with **"blowing dust"** — *"like when you blow out an old thing and dust
comes out"* (the old thing being a bellows), also "hoarse dust", "deep
hoarse breath". More accurate, his call. The description points somewhere
the ghost never did: a caw with the *shape* of a crow but breath-noise
where the voice should be — which reads as low harmonicity under a correct
envelope, exactly the per-burst harmonicity probe's territory. The tag is
`blowing-dust` in the pool vocabulary; "ghost" appears only in this file's
history, never in a stored answer.

## The second sitting — the tail was not the window's

Fresh clips (seeds from 1000, anchors past the first sitting's 56), same
design, graded under the new tag prompts with per-clip descriptions in
nearly every note (44 of 48). `analyse_sitting2.py`; the final 8 trials
ran back-to-back with dose 2 at Ben's request, recorded not hidden.

**P(longctx) = 0.568 [0.41, 0.71], margin +0.2** — the first sitting's
0.441 leaning-against becomes leaning-for. Pooled across both sittings:
**0.507 [0.39, 0.62] on n = 71 decided, margin 0.0 exactly** — the ear's
considered verdict on the 6 s window is a coin flip, not a cost. Length
check clean again (0.405, headwind if anything). Catches 6/8, 12/16
pooled. Two sittings 13 points apart on the same comparison is 0038's
listener drift doing what it does — one more reason no single sitting
gets to convict an arm.

**The cargo: his descriptions cross defect with arm, and the defect is
arm-independent.** Keyword families over his own per-clip words:

| family | longctx clips | twin clips |
|---|---|---|
| blowing-dust (bellows/breath/accordion) | 6 | 7 |
| machine (robo/modem/xylophone/beepy) | 9 | 9 |
| hoarse | 12 | 8 |
| scratchy-static | 8 | 10 |
| clean/real-sounding | 11 | 8 |

The bellows wheezes in both arms at the same rate. So the 0067 story —
"the window taught structure but bought an audible defect that cancels
it" — is dead: **the structure gains stand without an audible price, and
blowing-dust is a pipeline defect** (sampling, decoder, or codec — not
window, and not something the −2 tail of one 48-trial sitting could
localise). What it changed: the longctx arm comes off the bench — ear-tied
overall, structurally ahead on the gate, texture-tied per 0068 — and the
next lever is naming what blowing-dust is made of acoustically, for which
this sitting hands over ~88 per-clip-described generated clips as labelled
data (0069). The 9–12 s rung question reopens once the dust probe exists,
since "must first earn audibility at 6 s" has now been met with a tie
rather than a loss.
