# 0084 — where should I scout?

**Product name: CawScout** (chosen 2026-08-20) — the scouting stack as a
whole: the score, the targets, the predator and community layers, and the
visit marks. Sibling of CrowGPT and CawDex.

**Graduated 2026-08-22.** This experiment was the proof of concept; the
maintained implementation is `fieldserver/src/fieldserver/scout/` and one
command replaces the script chain here: `make -C fieldserver scout`
(fetch → score → assemble → validate → publish). Regions live in
`fieldserver.scout.regions`; the science below is still the record of why
each term exists. The scripts in this folder stay as the PoC history and
are no longer the way the layer gets built.

**2026-08-20** · build: three public APIs + a kernel grid · **answer: a ranked
target list, graded by field trips**

## The question

Random walks were not finding new families. This replaces them with a prior:
a 250 m grid over the valley scored on four signals — iNaturalist
research-grade American Crow observations (141; other people's eyes, weighted
highest), 0083's tall canopy stands, OSM greenspace (parks, cemeteries, golf,
turf — 7,997 features), OSM water (3,384) — with the home territory (kept
captures' centroid, 800 m) excluded and targets separated by 700 m so twenty
targets are twenty places.

Predators subtract (Ben's call, and correct ecology: Great Horned Owls are
the top predator of crow nests — the SLC cemetery recommendation he once got
was wrong for exactly this reason): 227 GHO observations at −0.30, Cooper's
Hawk density at −0.08. The penalty removed the University cluster from the
top five — campus raptors — and promoted the owl-free Taylorsville block.
Owl sightings draw on the map as purple dots so a cold zone explains itself.

The food-subsidy layer (2,481 OSM features: fast food, restaurants,
supermarkets, picnic sites, waste sites, the landfill; +0.15) came from Ben's
own null result: a walk through the Avenues found no crows, and the
literature says why — crow density tracks open turf and human food, and the
Avenues is steep, small-lot, food-poor, and sits against the City Creek owl
corridor. The layer promoted downtown's food-rich squares (Temple Square,
Gallivan Center, Library Square) alongside the sighting-verified Taylorsville
block; nothing in the Avenues ranks.

## Honesty box

This is a **prior, not a fitted model**. Its weights are guesses; its
validation is Ben's boots: every visit that finds crows (or doesn't) is a
label, and after a dozen trips the weights can be checked against outcomes.
Known warts: the tree signal normalises against a p99 dominated by the
canyon clusters, so urban stands read near zero and the ranking leans on
sightings + greenspace — the defensible pair anyway. The Cooper's Hawk fetch
queries both the old and new genus names and iNat resolves synonyms, so the
hawk layer double-counts uniformly — harmless after normalisation, untidy on
principle.

## Result — the top five, after the owls vote

1–2. The Taylorsville Memorial Park Cemetery / Taylorsville Park block —
   dense crow sightings, turf, Jordan River near, and not one owl record
3. An unnamed sightings hotspot west of it
4. Temple Square (water + sightings, light owl presence)
5. 6th East Park
The University cluster (Presidents Circle, Reservoir Park) led the
predator-blind ranking and fell out entirely once campus raptors subtracted.
Full list in targets.json; scout-map.html has all twenty numbered with
navigate links and the owl dots drawn.

## What it changed

Dawn trips have a ranked itinerary instead of a random walk. When a trip
happens, record the outcome (a capture at the spot is the natural log);
0084's follow-up is re-weighting against those outcomes once they exist.

## Revised 2026-08-20 — the west-side question, answered with district floors

Ben: "there's a ton of items on the west side of town… is that lack of
reports?" Measured answer: no — the nine west-of-Jordan targets have crow
signals at 1.00 (the Jordan River Parkway is genuinely birded and genuinely
crowed). What IS observation bias is the **owl penalty**: owl 0.00 across
every west target, while the east bench — the best-watched ground in the
valley — eats the −0.30 penalty precisely because its owls get reported.
The score punishes the places with the most eyes on them.

Two changes, one rerun:

1. **District floors.** Sugar House, Millcreek, East Millcreek, Holladay and
   Cottonwood Heights each get their best cell appended (ranks 21–25) if the
   open top-20 left them empty — Ben scouts the east side, and a target list
   he won't drive to predicts nothing. Radius 1,500 m: at 2,500 the Sugar
   House pin drifted to the radius edge and silently satisfied Millcreek too.
2. **run.py merges scout_layer.json instead of rewriting it** — a plain dump
   was about to strip the predator sightings and inline icons that
   build_predators.py parks in the same file.

Side effect worth naming: the trees signal now rides the 0083 layer that
includes OSM street trunks, and the reshuffle it caused agrees with the
field — **#1 is now 6th East Park**, the exact spot Ben independently called
"the spot" from the ground the same afternoon.

## Revised 2026-08-20 (later) — no east buff; the biases fixed instead

Ben asked whether to "buff the east side". A flat regional bonus would
hand-paint the answer onto the map, so the causes got fixed instead, and a
measurement decided which ones were real:

- **Birding effort is 2:1 east** (robin observations as the proxy: 66% east
  of the Jordan). So west crow reports at inat 1.00 on a third of the eyes
  are real presence — the crow signal stays raw.
- **The predator penalty now divides by local effort** (floor 0.3): reports
  per unit of looking approximates the true rate, so the east bench stops
  being penalised for being watched, and a lone owl report in an unbirded
  area counts for more, honestly.
- **Trees lead the weights** (0.32 vs inat 0.25): the satellite is the only
  instrument that measures both sides of the valley equally, and it says the
  east urban strip has 2× the canopy and 3× the nest-grade stands.

Outcome: 17 of 25 targets east / 8 west (was 11/9 of 20). The west survivors
are the Taylorsville–Parkway cluster, which the evidence genuinely supports.

## Field validation, running

- **2026-08-20, target #1 (labelled "6th East Park"):** Ben confirms prior
  crow sightings at the spot, independently of the model — he named it "the
  spot" from the ground the same afternoon the rescore promoted it to #1.
  His description ("just a road with a bunch of trees along it") matches the
  signals better than the label does: the `near` name is only the nearest
  OSM-named greenspace within 600 m, not what scored. First #1 with
  eyes-on-crows support; the pin's visit marks are the formal record.

- **2026-08-20, target #6 (Gallacher Park): null.** Ben visited, saw nothing,
  and judged the habitat "definitely plausible." Weak evidence weighted
  honestly: one visit, likely inside the mid-afternoon heat lull. Worth
  noting the model half-expected it — #6 carries the highest owl signal in
  the top ten (0.31 after effort correction), so "crow-shaped but empty" is
  its predicted failure mode. Marked-on-pin visits remain the formal record.

- **2026-08-20, target #13 (Taufer Park): null.** Same shape as #6 — nothing
  seen, habitat judged plausible. #13's standout signal is hawk 0.57, the
  highest Cooper's pressure in the top 15; like #6, the model's own negative
  signal offers the readiest explanation for crow-shaped-but-empty. Both
  nulls fell in the same mid-afternoon heat window, so time-of-day remains a
  confound across today's whole sample.

- **2026-08-21, target #4 (Library Square): CROWS, live.** Ben on site at
  11:30 am, THREE crows, notably docile — a pattern Ben has now seen twice at busy-road sites (here and State Street, South Salt Lake): heavy foot traffic habituates urban crows, shrinking their flight distance. Scouting consequence: loud sites trade noise floor for approach distance, and closer usually wins — every halving of distance buys ~6 dB of signal against a road that stays put. First live hit on a scouted visit (the #1
  confirmation was prior knowledge). #4's profile: green 1.0, food 1.0,
  inat 0.65, owl 0.01 — the predator-clean/food-rich shape both hits now
  share, against two nulls at the predator-heavy pins. Tally: 2 hits, 2
  nulls, and every outcome so far has leaned the way the signals leaned.

- **2026-08-21, families named.** The 6th East Park crows are now "The Red
  Liners" (after the TRAX line past their park) and the Library Square
  three are "The Scholars" — both created as families on the phone, both
  at top-three targets. Two days from layer launch to two named
  territories the recordist is following; the target list has started
  converting into the thing it was built to produce.
