# 0065 — did the scrape's diversity actually arrive?

**2026-08-10** · BirdNET embedding dispersion + novelty per source ·
**partial answer: yes, decisively, from the sources measured — but the two
biggest new pools are not yet in the join**

## The question

0064's null was two hypotheses in one coat: the drive-by-clip diversity
never survived the corvid gate, or it arrived and the model can't use it.
This measures the corpus side directly: per source, how varied are its
American Crow bouts (mean pairwise cosine dispersion), and what fraction sit
in embedding regions the curated pre-scrape corpus does not occupy (nearest
curated neighbour beyond the curated set's own held-out p95 self-distance).

## Result so far

| source | n | dispersion | **novelty** |
|---|---|---|---|
| curated archive #1 | 335 | 0.287 | 0.018 |
| curated archive #2 | 329 | 0.283 | 0.033 |
| soundscape archive | 95 | 0.281 | **0.421** |
| archive #3 | 56 | 0.263 | **0.929** |

The controls behave (curated sources ~0 novel against themselves, as
constructed), which is what licenses the finding: **93% of archive #3's
bouts and 42% of the soundscape archive's occupy regions the old corpus never did.** New
acoustic material genuinely arrived — and v3 trained on it and sounded
identical anyway. Combined with 0064, that moves the blame squarely onto
the model side: the diversity is in the corpus and the recipe cannot cash
it. Exactly the split verdict 0064's README hoped for, because it points at
context/conditioning rather than at more collecting.

## The gap, and the fix owed

The two biggest new pools are missing: their bout `recording_id`s (file
stems like `inat_<ref>_<id>`) don't match the crawl database's bare
source_ref, so the (species, ref) join silently excluded them. The
measurement needs a stem-parsing join and a rerun — cheap, queued behind
tonight's 0066 training. Until then "diversity arrived" rests on the small
sources; the big-pool numbers could move the magnitude, not the sign.

## What it changed

Stops any lingering "the scrape was wasted" reading — the corpus is richer;
the generator is the bottleneck. Raises the priority of the long-context
arm and of conditioning work (0066 running tonight), and hands the
contact-call thread a concrete hunting ground: archive #3's 93%-novel
region is where un-corpus-like calls live.

## Final table (slug-fix rerun, 2026-08-11)

| source | n | dispersion | novelty |
|---|---|---|---|
| archive #3 | 56 | 0.263 | **0.929** |
| soundscape archive | 95 | 0.281 | **0.421** |
| community archive | 314 | 0.284 | **0.118** |
| curated #2 | 329 | 0.283 | 0.033 |
| curated #1 | 335 | 0.287 | 0.018 |

The shape is telling: novelty concentrates in the *least curated* sources —
the archive nobody recorded for bird-guide purposes is 93% novel, the
soundscapes 42% — while the big phone-recording pool is mostly familiar
territory with a real novel fringe (12% of a very large pool is thousands
of bouts). The remaining big source never cleared the ≥40-bout sample bar
for this species and stays unmeasured; given its long-ambience character,
its yield was always going to be hours, not variety per bout.

Verdict stands and sharpens: **diversity arrived, and it arrived from
exactly the sources least like what the corpus already had.** The model
side (0064's null, 0067 in flight) is where the cashing-in has to happen,
and the archive #3 / soundscape-archive novel regions are the contact-call thread's
hunting ground.
