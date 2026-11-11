# 0089 — Are clips shared by Instagram crow accounts worth asking for?

**Question.** Ben got ten phone videos from a London crow enthusiast, with a
spreadsheet saying what each call was and what was happening. Collecting more
this way is slow (one DM conversation per account). Is the result worth it?

**Data.** Shared batch `instagram-2026-11`, captures 199–208 on the hosted
server: 10 clips, 3.2 minutes, London Carrion Crows, imported with
`fieldserver/tools/import_shared.py`. Compared with Ben's 29 kept field captures
(24.7 min). `run.py` reads the pipeline's own numbers from the field database;
`unfiltered.py` reruns the analyzer on the same stored audio.

## Results

| | shared (10) | Ben's kept (29) |
|---|---|---|
| median band SNR | **33.4 dB** | 19.1 dB |
| labels per minute | 3.2 | 2.7 |
| context events per minute | 6.0 | 6.5 |
| BirdNET hears a crow (as the worker ran it) | **1 / 10** | 24 / 29 |
| BirdNET hears a crow, no occurrence filter | 8 / 10 | — |

1. **The audio is better than ours.** Fourteen dB more band SNR than the
   kept field captures: phones held near birds that walk up to a feeder they
   know.
2. **The context is as dense as ours.** About six context tags a minute,
   the same as Ben's labelling, plus what our tags can't hold: named
   individuals, territories, who was trespassing on whom. Reginald is on two
   different days, which is the first cross-day individual pair in the
   corpus.
3. **The worker missed nine of ten, and that was our bug, not the clips.**
   It gave every capture with no GPS the fleet's Utah coordinates, so
   BirdNET's occurrence filter removed Carrion Crow. Fixed in f69f6e8
   (`FIELD_REGION`); any region-only contributor outside Utah would have hit
   it.
4. **Without the filter, BirdNET can't tell Carrion from Hooded.** It splits
   nearly every clip between the two. Giving it London's coordinates
   (`--lat 51.5 --lon -0.12`) changes nothing, because its range map has
   Hooded Crow in Britain too. So geocoding regions would not fix species
   for this population; the recordist's species is the ground truth.
5. **The call-type heads can't hear what this batch is about.** With no
   filter, of 51 confident crow regions the heads called 48 "call", 2
   "flight call" and 1 "alarm call". The two mobbing clips came back as "call", the begging clip
   as "call", and the rattle (clip 4) and the cleanest tonal caws (clip 10)
   were not detected at all. Every one of those is a class that has few or no
   Carrion Crow field examples.

## Answer

**Yes, worth asking for, and for specific things rather than more caws.**
The clips are cleaner than our own recordings and carry richer context. What
the models can't do here is exactly what this batch labels: begging, mobbing,
rattles and named individuals. Ten clips can't retrain a head; they can show
where it fails. Plain contact caws are the class the models already handle,
so the useful ask to the next accounts is:

- clips of the same named bird on different days and in different situations;
- anything with a visible trigger (raptor, dog, intruding crow, food);
- rattles, begging and juvenile practice calls;
- a spreadsheet like this one, which turned out to be the most valuable part.

## What it changed

- Found and fixed the home-ground fallback in the analyze worker (f69f6e8).
  This matters more than the batch itself, since every non-Utah region-only
  contributor would have hit it.
- Added `captures.provenance` and `captures.generator_excluded` (revision
  0035), so a recordist's terms are stored in the data, not just in an
  email.
- Decided **not** to geocode region names for the occurrence filter: for
  the one population tested it doesn't fix the species error it was meant
  to fix.
