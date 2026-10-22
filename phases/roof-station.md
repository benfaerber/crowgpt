# The work-roof feeding station

> **Status: designed, nothing built.** Ben, 2026-08-04: a feeder station on the
> roof of his workplace. This is the design and the staged build, with the gates
> that stop each stage before it wastes the next.

`data-collection.md` already describes a **Mode 1 roof station** — a trail cam and
an always-on mic at the apartment window, aimed at the flat roof where the Poe
Family takes peanuts. This is not that. That one watches birds we know, from
inside, at home. This is a **second site, a second family, and an unattended
recorder**, and the differences are what make it worth building rather than a
duplicate.

## Why this is worth building, in the order the reasons matter

Three of these are things nothing else in the project can produce, and the first
one is the reason to do it at all.

**1. It is the only way to record these birds with no human in the recording.**
`FUTURE.txt` — "Every recording in the corpus was made by a bird's feeder" —
`observer_role` across all field captures is `feeder` (6) and `feeding_now` (7)
and nothing else. There has only ever been one person holding the phone, so "a
known feeder is present" is perfectly confounded with "a recording exists". Every
baseline in this corpus is a baseline with Ben in it.

A station breaks that by construction rather than by recruitment: put food down,
walk away, and the recorder keeps running. The birds arrive to food with nobody
there. That is a class of audio the corpus has zero of and cannot get any other
way — recruiting neighbours (the plan in `FUTURE.txt`) gets a *different* human,
which is a good control for familiarity and no control at all for presence.

**2. It manufactures the negatives the head has no idea it needs.** Experiment
0036's largest finding is in `TODO.txt`: handed 572 segments a labeller marked
crowCount=0, the shipped four-class American Crow head assigns a call type at
p > 0.5 to **97.0%** of them, mean top probability 0.898. It has no abstain, so on
silence it guesses confidently. The same entry: "Field negatives are better still
and cost almost nothing to collect."

An unattended station running four hours a day produces field negatives by the
hour, from the exact microphone, the exact site and the exact noise floor the
positives come from — which is what makes them useful and what a crow-tools
garbage set can never be. This is the cheapest large win on the list and it is a
by-product of leaving a recorder on.

**3. It targets the one common call the corpus does not contain.** `FUTURE.txt`,
closing the mobbing entry: "the corpus's `call` class is a rattle detector.
Contact calls are the most common crow vocalisation and the corpus contains none,
so the class the field will exercise hardest is the one trained on something
else." `contact_call` is already in the vocabulary and empty.

Arrivals at a feeding station are where contact and food-associated calling
happen. Birds come in ones and twos, call to each other on approach, take a
peanut and leave — and the leaving is what brings them back, which is why in-shell
peanuts matter below.

**4. A second family is a test set, not more training data.** Everything the
project knows about wild crows comes from five birds in one territory. Whether a
call type learned on the Poe Family transfers to an unrelated family a few miles
away is the dialect question, and it is unanswerable with one family. Treat this
site's labels the way 0036 says to treat field mobbing labels — as something that
can *falsify* a number, not as volume.

**What it is bad at, and this is not a small caveat.** A station has no witnessed
context. Nobody saw what the dog was doing. Context events are the only thing that
can answer what a call is *about*, and this station will produce almost none of
them — the camera restores a fraction, after the fact, for whatever happens in
frame. So this feeds the **acoustic** problem (README problem 1) and the abstain
problem, and it barely touches **semantics** (problem 2). It does not replace
handheld sessions and it must not be allowed to look like it does.

## Gate 0 — are there crows on this roof at all?

**Build nothing until this is answered.** The most expensive failure available
here is a station on a roof no crow visits, and it costs one week of looking to
rule out.

For a week, at the time you would feed: go up, look for five minutes, write down
what you see. Crows in the airspace, crows on the parapet, crows on any
neighbouring roof or the trees in the street. Record 60 s of ambient at two or
three candidate spots while you are there — that doubles as the noise survey
below.

Pass: crows seen on or adjacent to the roof on most days. Marginal: crows visible
in the neighbourhood but never on the building — still workable, feeding will
often pull them in within a fortnight, but expect the acclimation to run twice as
long. Fail: no corvids at all in a week. Downtown SLC has plenty of crows, and it
also has blocks that belong entirely to gulls and pigeons.

Worth knowing about timing: SLC crows form large communal winter roosts, so a
downtown roof gets substantially more corvid traffic from late autumn than in
August. Starting the habituation now means the station is already familiar
furniture when the numbers arrive.

## Permission, and the things that actually end this

Ordered by how likely each is to end the project.

- **Written permission from the building owner or facilities, before anything
  goes on the roof.** Not a favour from a colleague with a key. Ask for roof
  access and for a small unattended structure, and say plainly that it involves
  bird food and a camera — a permission granted on a partial description is worth
  nothing the day someone objects.
- **No roof penetrations. Ever.** A screw through a membrane voids the roof
  warranty and creates a leak somebody else pays for. Everything is ballasted or
  tethered to existing rooftop steel with approval. This constraint drives most of
  the build below.
- **Fall safety.** Keep the station at least 3 m back from any unprotected edge or
  skylight. This is a daily visit in the dark half of the year, and the reason to
  site it back from the parapet is that you will otherwise be standing at a roof
  edge every morning while carrying things and thinking about crows.
- **The camera must see only the roof deck.** A camera on a commercial roof that
  frames neighbouring windows, a street or an entrance is a privacy and HR problem
  that has nothing to do with birds, and it is the version of this that gets you
  told to remove everything. Angle it down; frame the perch, the tray and a sliver
  of sky, and nothing beyond the parapet line. `data-collection.md` wants "the
  roof edge + a sliver of sky/street" for mobbing airspace — take the sky, drop
  the street.
- **Label the station.** A weatherproof tag with name, what it is, and who
  approved it. Unattended equipment on a commercial roof that nobody can identify
  gets removed, and possibly reported, and you find out when it is gone.
- **Check the SLC and county ordinances on feeding wildlife.** Many cities
  restrict feeding that creates a nuisance, and "nuisance" in practice means
  gulls, pigeons and rodents rather than crows.
- **American Crows are protected under the Migratory Bird Treaty Act.** Feeding is
  fine. Banding, trapping, handling, keeping a feather, or disturbing a nest are
  not, and banding specifically needs a federal permit. This closes the tempting
  shortcut for individual ID — see below for the one that is legal.
- **Spring is different.** A nesting pair defends fledglings by dive-bombing, and
  a workplace roof is somewhere colleagues go. Find out before March whether
  anything nests on or beside the building, and be prepared to pause the station
  through fledging rather than have the project introduce itself to the building
  as the thing that makes crows attack people.
- **Stop feeding if birds look sick or you find a dead corvid.** Concentrating
  birds at a shared surface concentrates disease, and corvids are hit hard by
  avian influenza. Clean the tray, and report a dead corvid to the state wildlife
  agency rather than moving it yourself.

## Gulls, pigeons and rats — the design problem the birds are not

On a downtown SLC roof, gulls are not a footnote. California Gulls are abundant,
they find food visually from the air, they are faster to exploit a novel food
source than a neophobic crow, and they will displace crows from a tray. Pigeons
are second. Rodents are third and are the one that generates a complaint you
cannot argue with.

The design answers each differently, and the ordering is deliberate — the strong
anti-gull measures are all deferred, because on day one **neophobia is a bigger
risk than gulls** and every deterrent is also a deterrent to the birds you want.

- **In-shell raw unsalted peanuts as the only routine food.** This is the main
  filter and it is free. Pigeons cannot handle a shell. Gulls will take them but
  they are a poor gull food compared with anything soft, so the station is not
  worth defending to a gull. Crows handle them easily, and — the part that matters
  for audio — a crow takes one and *leaves* to cache it, then comes back. Turnover
  is arrivals, and arrivals are calls.
- **Never kibble, bread, meat scraps or anything soft.** Dry cat and dog kibble is
  the other classic crow currency and it is exactly the gull and rat magnet to
  avoid here. This is a workplace roof, not a garden.
- **A small portion, and nothing left behind.** Fifteen to twenty-five peanuts:
  worth the trip, gone inside ten minutes, and nothing to find at midnight. On the
  next visit, sweep up any shells and uneaten nuts. Food left overnight is how the
  rodent complaint arrives, and the rodent complaint is what ends this.
- **A canopy over the tray, if and only if gulls become a problem.** Deferred to
  Phase 2 for two independent reasons: it is a second novel object during
  acclimation, and it is a sail on a windy roof. Its real mechanism is visual —
  hiding food from birds circling above matters more than the headroom does.

## The build

Everything is ballasted, nothing is fixed to the roof, and the whole thing can be
carried up in two trips and taken down in ten minutes.

```
                    ┌────────────────────────────┐  ◄─ canopy — PHASE 2 ONLY
                    │                            │     750 × 600, ≥300 clear
                    └────────────────────────────┘
    ▓▓▓ perch bar, Ø35 mm, ~900 long
    ║
    ║  1400                      ┌──────────────────────┐  ◄─ tray 600 × 450
    ║   above deck               │▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│     mesh floor, 50 lip
    ║                            ├───┬──────────────┬───┤
    ║        mic ● ──────────────┤   │              │   │  ◄─ legs, 500
    ║      400 high, aimed       │   │              │   │
    ║      at the perch          │   │              │   │
  ══╩══════════════════════════ ═╧═══╧══════════════╧═══╧══
     paver ballast                    paver ballast
  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   roof membrane
                                                              — no penetrations
       ◄────── 1200–1500 perch to tray ──────►     (mm throughout)
```

**The tray.** 600 × 450 mm, a 50 mm lip so nuts do not roll off, floor of 12 mm
galvanised hardware cloth rather than board. Mesh is the standard for platform
feeders because it drains — a solid tray ponds water, and a roof already has
enough of that argument. It also hoses clean, which the disease note above makes
a weekly job rather than an occasional one. Legs 500 mm: clear of meltwater and of
the heat radiating off a membrane that hits 60 °C on an August afternoon, low
enough to keep the wind profile down.

**Do not build a hopper, a tube or anything with a perch ring.** Crows do not
cling and do not feed from songbird furniture. An open platform they can land on,
see out of, and leave in any direction is the entire requirement — a bird that
cannot see its escape route does not land.

**The staging perch is where the recording actually happens**, and it is the part
most likely to be left out. Crows land near food, assess, call, and then drop
down; at the tray itself they are eating and quiet. So the calls come from a spot
1.2–1.5 m away and *above* the tray. Give them one deliberately — a 35 mm bar at
1.4 m — instead of letting them choose a parapet 15 m away, and you have fixed the
one variable that decides the audio: distance to the microphone.

**Ballast and wind.** Two 400 × 400 paving slabs, ~18 kg each, on a plywood base
the legs bolt through. That is enough for ordinary weather and **not** enough for
a canyon-wind event once a canopy is on it — a 750 × 600 panel at 30 m/s
broadside overturns this base comfortably. So: the canopy is bolted rather than
clipped, the whole station is tethered with steel cable to existing rooftop steel
(HVAC curb, parapet anchor — with facilities' approval), and on a forecast wind
event the answer is to go up and lay it flat. A station that departs a roof in a
gust is a permission conversation you do not recover from.

**Water may matter more than food here.** August in SLC is hot and dry, and a
shallow dish — 250 mm across, 30–40 mm deep, in shade — can out-pull peanuts and
attracts almost no rodents. Dump and refill daily; never leave standing water on a
roof.

### Rough bill of materials

| Item | Note | ~USD |
|---|---|---|
| Timber / HDPE for tray and frame | exterior grade, or an offcut HDPE board | 40 |
| 12 mm galvanised hardware cloth | tray floor | 15 |
| 35 mm dowel or rail + post | the staging perch | 15 |
| 2 × concrete paver, plywood base | ballast | 25 |
| Steel cable, turnbuckle, shackles | tether to existing steel | 25 |
| Shallow water dish | glazed or HDPE, not metal | 10 |
| **Recorder** — Zoom H1essential | 32-bit float, per `data-collection.md` | 100 |
| Fur windjammer for it | not optional on a roof | 30 |
| Weatherproof housing / dry box | recorder and battery | 30 |
| **Cellular** trail cam, WDR | see below on why cellular | 150 |
| Peanuts, unsalted, in shell | per 10 kg | 30 |
| | | **~470** |

## Acoustics — the part this project is actually for

**Wind is the whole problem, and this roof is the worst place available.**
`TODO.txt` carries the open entry: no experiment has ever sampled wind, 0005 and
0010 both concluded about wind protection on days that had none, and it notes
directly that this "bears on the mounted-camera plan too: a phone propped at the
perch sits in whatever wind is there, where a handheld one is partly shielded by
the body." A station is that worry made permanent.

What follows from it:

- **Mount the mic low, not high.** 400 mm, aimed up at the perch. Height buys
  nothing at 1.2 m range and buys wind noise at every height.
- **Full fur windjammer over foam, permanently.** Whatever the deadcat costs in
  the caw band, it is smaller than what a roof gust does to a recording.
- **A low windbreak panel on the prevailing-wind side**, sited so it shields the
  microphone without standing between the microphone and the perch.
- **Survey the noise floor before choosing the spot.** Roofs are covered in
  continuous machinery, and an HVAC unit 5 m away is a wall of broadband noise
  that no amount of windshield fixes. Record 60 s at each candidate spot during
  Gate 0 and compare absolute band energy — this is a real measurement and belongs
  in `experiments/` rather than in a judgement call on the day.
- **Judge it on crest factor and noise floor, not band SNR.** The `TODO.txt` entry
  is emphatic and the reason is structural: band SNR is a percentile ratio *inside*
  one recording, so when the floor is pinned high the quiet percentile rises with
  the loud one and the ratio barely moves. It produced a confident wrong answer on
  exactly this comparison once already.

**The distance win is large and worth stating.** Field recordings in this corpus
are made at 5–20 m. A station perch at 1.2 m is 12–24 dB of signal over that,
before any other improvement. If the wind is handled, station audio will be the
best-SNR corvid recordings the project has, by a wide margin.

**32-bit float is the reason to buy the recorder rather than leave a phone up
there.** A caw at 1.2 m is loud, unattended means nobody rides the gain, and a
clipped caw is gone. `data-collection.md` already picked the H1essential for
exactly this. A phone would also want charging, weatherproofing, and — per the
open `TODO.txt` entry — is the device whose microphone pinning is currently
unreliable when inputs change mid-session.

**Run the mic continuously and independently of the camera.** This is already
decided in `data-collection.md` and it is the single most valuable line in it:
motion triggers miss caws when the bird sits still. Cam = context, mic = the
calls, neither depending on the other's trigger.

**The camera should be cellular, not WiFi.** `data-collection.md` specifies WiFi
for the home roof, and a workplace inverts that: a camera on the corporate network
is an IT conversation, a security-review conversation, and a device somebody else
can turn off. A cellular trail cam needs no permission from anyone but the
building. Keep WDR — it is still the one spec that matters, because a dark crow on
a bright roof is a blown-out exposure and also, helpfully, a trivial detection
target.

**Individual ID is legal by camera and not by band.** Banding needs a federal
permit; a fixed camera at a fixed distance, photographing the same birds daily,
gets you plumage gaps, missing primaries, molt state and bill and leg marks. Those
IDs are seasonal rather than permanent because birds molt, which is a real
limitation and still infinitely more than handheld recording has ever supported.
This is the per-bird data `data-collection.md` wants for the dialect question.

## The daily protocol, and the trick inside it

Same spot, same time, every working day. Crows learn a schedule within days and
will be waiting before you arrive, which is the entire mechanism that makes a
station out-yield walking around hoping.

**Put the food down and leave immediately.** Do not stay to watch. This is the
design's one real trick and it is what buys reason 1 above: the recorder runs, the
birds come to food, and there is no human in the recording. Watch it on the
camera afterwards.

It also gives a clean pair for free, over the same birds at the same site with the
same microphone:

- **you present** — the two minutes you are on the roof putting food out,
  `observer_role = feeding_now`
- **you absent** — the twenty minutes afterwards when they actually feed

That comparison is the confound in `FUTURE.txt` stated as an experiment, and no
part of it requires anything beyond leaving the recorder running while you walk
down the stairs.

Recording window: from just before you arrive to roughly ninety minutes after.
Everything outside that is negatives, which are worth having — but a scheduled
block keeps the data volume sane and the battery alive.

## What this does to the data model — decide before the first upload

**A station will produce more captures in a fortnight than the corpus has in its
entire life,** and that breaks things quietly rather than loudly.

`CLAUDE.md` is explicit that the ★ Keep flag is the only thing separating genuine
field recordings from seeded archive clips and test uploads, and that any count
not filtered on `keep` describes the pipeline rather than crows. Station audio is
genuine field recording. If it arrives as ordinary kept captures, then every
existing number silently changes meaning, the 14 hand-kept recordings drown in
station traffic, and the calls × context matrix fills with rows that have no
witnessed context behind them.

So, before a single station capture is uploaded:

- **A `source` on captures** — `handheld`, `station`, `seed`, `upload` — so
  "recorded by a person in the field" and "recorded by a box on a roof" are
  separable at query time. `keep` cannot carry this: it means "this is real", and
  station audio is real *and* different. **No wire bump needed**: the phone never
  sends it, the server defaults phone pushes to `handheld`, and the station's own
  ingest path sets `station`.
- **An `absent` observer role**, "Nobody there". `observer_role` describes the
  human present, and NULL already means "not recorded". Writing NULL for "there
  was demonstrably nobody" would conflate unknown with none, which is the mistake
  this repo has now written down three separate times — `config_version` NULL,
  `band_snr_db` NULL, and the `not_a_crow` versus `none` distinction in `TODO.txt`.
  Server-side only: a `SEED_OBSERVER_ROLES` entry and a translation, no migration
  and no app build, reaching the phone through `GET /api/config` on relaunch.
- **A segmentation step, because a four-hour block is not a capture.** The app's
  model is that a capture *is* a sighting with audio attached. A continuous block
  is neither. The pipeline that fits what already exists: block → `analyzer/`
  (a path in, findings out, no server, no DB) → corvid detection windows → a
  capture per region, pushed with `source = station`. The negatives are the
  complement — the confirmed-empty stretches — and are worth keeping as blocks
  rather than as captures, because they are training material and not sightings.

## Staged build, with the gate that stops each stage

Crows are neophobic. A novel object takes days to weeks to be accepted, and the
failure mode is not subtle — the birds simply stop coming and you conclude there
are no crows on this roof. **Every stage waits for the birds to be reliably taking
food before the next begins**, and only one thing changes at a time. Putting the
platform and the camera up on the same day means you cannot tell which one spooked
them.

| | What changes | Gate before moving on |
|---|---|---|
| **0** | Nothing. Look, and record ambient at candidate spots. | Corvids seen on or near the roof most days |
| **1** | Food only, on the bare roof, same spot, same time | Food reliably taken within a week |
| **2** | Platform present, food still on the deck beside it | Birds feeding calmly with it there |
| **3** | Food moves onto the tray; perch bar goes up | Birds using the tray and the perch |
| **4** | Recorder, in its housing, switched off | Birds unbothered by the new box |
| **5** | Recorder on. **Data starts here.** | Usable audio; noise floor as surveyed |
| **6** | Camera | Birds unbothered; frame checked for the roof deck only |
| **7** | Canopy — *only if gulls have arrived* | — |

Stages 1–3 realistically take three to six weeks at a fresh site with no history.
That is not slack in the plan, it is the plan; a station rushed to stage 5 in a
week records an empty roof.

## Decided not to

- **A hopper, a tube, or any feeder with a perch ring.** Crows do not use them.
- **Kibble, bread or soft food.** The gull and rodent risk is the thing that ends
  a workplace station, and in-shell peanuts do the same job while filtering
  pigeons for free.
- **Leaving food out overnight**, in any quantity, for any reason.
- **The canopy on day one.** Two independent reasons — a second novel object
  during acclimation, and a sail on a windy roof — and it solves a problem that
  may never arrive.
- **A WiFi camera**, unlike the home-roof plan. Cellular avoids the corporate
  network entirely.
- **Banding for individual ID.** Federal permit; the fixed camera is the legal
  route and is good enough.
- **A phone as the recorder.** No gain safety, needs power and weatherproofing,
  and its microphone pinning is a live open bug.
- **Playback of any kind at this station.** `FUTURE.txt` has the ethics gate on
  playback and it applies harder here: a habituated family is a ruined study as
  well as a wronged one, and a station is the one place you could accidentally run
  an uncontrolled playback experiment every day.

## Experiments this makes possible

Each is a numbered folder with a `run.py` and a `README.md`, per the project's own
rule, and each answers something currently open.

- **Settle the windshield on a windy day.** The standing `TODO.txt` entry, which
  has never been run because no experiment ever sampled wind. A station can run two
  matched mics side by side, one jammed and one bare, for an entire windy day —
  which handheld A/B could never do, and which is why the existing answers are
  assertions rather than measurements.
- **The roof noise-floor survey**, before siting the mic. A measurement that
  precedes a build.
- **Does the same bird call differently when nobody is there?** The you-present /
  you-absent pair above, against the confound that touches all 13 existing field
  recordings.
- **Field negatives for an abstain class.** Hours of confirmed-empty roof audio,
  aimed directly at 0036's 97%-confident-on-silence finding.
- **Do the Poe Family's call types transfer to an unrelated family?** The dialect
  question, with this site's labels used as a test set that can falsify a number
  rather than as training volume.

## What this changed

Nothing yet — nothing is built. The design changed one thing already, which is
worth recording: the reason to build this moved from "more recordings" to
"recordings with no human in them", and that reordered the whole plan. It is why
the protocol says put the food down and leave, why an `absent` observer role has
to exist before the first upload, and why the station is worth the permission
conversation even if it never yields a single labelled call.
