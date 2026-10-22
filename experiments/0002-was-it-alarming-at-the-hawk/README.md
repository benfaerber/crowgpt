# Were the crows alarming at the hawks?

**2026-07-26** · captures 87 and 88

## Why

The recordist recorded a single crow calling from a rooftop, walked home, and
five minutes later saw two hawks from an apartment window about a block away.
Reasonable hypothesis, and exactly the kind that quietly becomes a "finding" if
it is written into the ground truth.

## Method

Two independent questions.

1. Did a raptor vocalise? Re-ran BirdNET over both recordings at
   `min_conf=0.03` — thirty times lower than production — with the location
   filter both on and off. The production analyzer keeps only corvid rows, which
   is right for the corpus and wrong for this question.
2. Is the calling structured like mobbing? Measured onsets, durations and
   inter-call intervals.

## Result

**No raptor, at any threshold, filtered or not.** The only non-crow candidates
were Black-crowned Night-Heron at 0.19 and 0.16 — near-certainly the model
misreading a crow caw, whose "quok" is acoustically close — and a Great Horned
Owl at 0.034, which is noise.

That is weak evidence though: **hawks are usually silent**, especially perched or
hunting. "No hawk vocalisation" is close to no information about presence.

The calls themselves say more. The call-type head returns **alarm call** on both,
`crow_conf` 0.976 and 0.896. Capture 88 has two clean bouts — four caws at
3.43/3.87/4.35/4.93 s, then three at 9.35/9.82/10.35 s. That is **~0.48 s
spacing held to within 0.05 s**, in short 0.15–0.20 s caws: metronomic scolding
cadence, textbook American Crow alarm.

But it does not look like mobbing. One bird, ~20 calls/min, a 12.4 s gap
mid-clip, and a stop long enough that the recordist thought it had finished.
Mobbing is relentless and recruits others.

## What it changed

The capture was **not** tagged `raptor_overhead`. Tagging an inferred cause would
have made the calls × context matrix report "alarm calls co-occur with raptors"
by construction — true because it was assumed, and indistinguishable a year later
from a result that was earned.

It directly motivated the **sightings** table: something seen near a recording
but not during it, stored where it cannot reach the matrix, with a required
signed time offset. The hawks are recorded as a lead, which is what they are.
