# 0064 — does the scrape change the sound?

**2026-08-09, predictions written before any result existed** · build running
overnight · **answer: pending**

## The question

The 2026-08 scrape added ~180 GB of audio from five new sources — the big
pools being ~23,000 passive phone recordings and long field recordings from
sound libraries — where the old corpus was almost entirely recordist-curated
archive clips. v3 = the incumbent's exact recipe (d384/L8/H6, dropout 0, 30k
steps, EnCodec K=8) on the re-extracted corpus. Only the corpus changes.

## The two predictions, on the record

**Ben's:** the new sources carry more *call diversity* than curated clips —
a recordist's short upload is a drive-by of whatever was loud and obvious,
while a long passive recording catches the full repertoire including the
quiet social calls the corpus is known to lack. So v3 should be audibly
better, or at least more varied.

**The prior from 0048/0050:** null. Corpus scaling is exhausted — each
doubling buys a third of the last, the 25→45 GB expansion was a dead heat by
ear (0.51), and the new material is +34% American Crow detected hours, well
under a doubling. Composition read by the call-type head looks *more*
alarm-heavy, not less — though that head bins unfamiliar audio into `alarm
call` (0036), so it cannot adjudicate Ben's hypothesis in either direction.

The interesting outcome is the split verdict: diversity measurably arrived
(below) but the sound didn't change — which would point at conditioning or
context length, not data, as the binding constraint. Note also what this run
CANNOT test: bouts are capped at 3 s, so any structure long recordings carry
*between* calls is discarded before training. That is a separate future arm.

## Measurements, in order

1. **Composition delta** (after extract): bouts and hours by species and
   source, v3 store vs `bouts.pre-v3` snapshot.
2. **Did diversity actually arrive** (the direct test of Ben's claim):
   per-source bout dispersion in embedding space — do new-source bouts
   occupy regions the curated corpus doesn't? Doubles as the candidate-mining
   groundwork for the contact-call thread (0060–0062, FUTURE's trainer
   entry).
3. **v3 vs v2 by ear**, 0050-style side-balanced sitting — and BOTH arms
   decode through the same decoder. 0063's adversarial finetune is the
   presumptive vocoder if Ben's listen confirms it; decoding the two models
   through different decoders would confound everything.

## Build

`crowgpt/tools/v3_overnight.sh` under transient unit `crowgpt-v3` (no
auto-restart on purpose — extract/tokenize don't resume). Progress on the
dashboard. v2 preserved: `bouts.pre-v3` hardlink snapshot, standing token
dir untouched, checkpoint to `results/model-v3-scrape`.

## Result — the null, for the third time, and now beyond argument

**P(v3 preferred) = 0.457, CI [0.32, 0.60]** over 46 decided compares (v3 21,
v2 25, ties 4). The pool blocks' graded margin agrees to the decimal: mean
+0.03 toward v3 on a ±2 scale, distribution symmetric (12×+1 v3, 13×+1 v2),
and mostly magnitude-1 answers — differences audible but slight, favouring
nobody. First-heard bias 0.522 [0.38, 0.66]: the instrument ran clean.

So: tripling the corpus to 105.8 h across 69 species, with American Crow
itself up 53%, changed the sound **not at all** — the same coin flip 0050
got from +57%. With 0048's scaling curve, 0050, and now this, corpus volume
for this recipe is closed as a question. Ben's diversity prediction loses
this round *as stated*; what survives of it is the part this run could not
test (bout-cap 3 s discards between-call structure) and the part not yet
measured (did embedding-space diversity actually arrive? — still the next
measurement, because "diversity arrived but the model can't use it" and
"diversity never arrived" point at different follow-ups).

**The finding that was not the question: catches went 7/10.** Real preferred
over generated only seven times in ten, against 10/10 (0050) and 10/11
(0053). Both readings deserve the page: (a) through the finetuned decoder,
typical generated clips are now genuinely hard to tell from real — Ben's
own block-1 note ("both are really damn good") says as much; (b) the pool's
anchored-timbre question may let a *clean* generated caw beat a *noisy* real
field recording on "closer to the reference" — a confound 0050's blunter
question didn't have. A clean-vs-noisy catch design would separate them if
it ever matters.

Defect tags went entirely unused across 33 graded trials — either nothing
rose to tagging or the UI didn't invite it; worth one question to Ben
before the next pool.

**What it changed:** stop buying corpus for the generator, permanently; the
GPU goes to context length / conditioning / structure next (the 0024
pulse-density defect and the 3 s bout cap are the standing suspects). The
scrape retains full value where composition matters — the contact-call
thread (0060–0062), the ear trainer, and any long-context arm all feed on
exactly what it brought.

## The sitting's two instruments, recorded before the analysis

Block 1 (20 trials) was answered on a standalone PairPage — built before its
author knew the field server's pool system existed — and is banked at
`crowgpt/results/listening/pairwise-0064/`. Blocks 2–3 (40 trials, 7 catch)
were lifted out of that page byte-for-byte by `migrate_to_pool.py` and
registered as pool `scrape-v3-0064`, graded from the dashboard like every
sitting after this one (see CLAUDE.md's new rule, which this near-miss
wrote). Blocks 2–3 gain per-trial real anchors and the graded −2..+2 scale;
the merge maps grades to their sign. Block 1's own engagement notes: 2/3
catches, first recorded catch miss since 0053 — read with Ben's note that
"both are really damn good" through the new decoder.
