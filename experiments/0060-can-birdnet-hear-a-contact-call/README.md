# 0060 — can BirdNET hear a contact call as a crow?

**2026-08-09** · 78 contact bouts vs 381 alarm bouts, species-matched ·
**answer: yes, at the same rate as alarm calls — the finder for contact
bouts already exists**

## The question

Ben, after the ear trainer shipped and he had learned the sound: if BirdNET's
species detection fires on contact calls, the existing corpus scan becomes
the contact-bout *finder* and his trained ear the *filter* — the call type
the classifier head cannot see (FUTURE's contact entry) could be surfaced
without a head existing yet. If BirdNET is deaf to them, finding candidates
needs the embedding route instead.

## Method

The trap avoided: the trainer's contact clips were cut *from* BirdNET
detection windows, so scoring those would measure BirdNET on audio BirdNET
already liked. Here every recording was segmented by 0013's energy detector
(corvid-band bursts against the recording's own floor, the validated 12 dB
threshold — no BirdNET anywhere in it), and every bout got a 3 s window
scored for max corvid confidence through `crowgpt.birdnet`.

Arms matched by species (Hooded Crow, Northern Raven), both
recordist-asserted at the recording level, seeded sample of alarm recordings
to the contact arm's counts, both capped at 120 s per recording:

- **contact** — all 28 downloaded recordings whose recordist said contact
- **alarm** — 28 recordings by the same species asserting alarm, the call
  type BirdNET is known to find

## Result

| arm | bouts | ≥ crow_min (0.25) | ≥ 0.5 | conf quartiles |
|---|---|---|---|---|
| contact | 78 | **84.6% [75.0, 91.0]** | 75.6% [65.1, 83.8] | 0.52 / 0.79 / 0.93 |
| alarm | 381 | **84.0% [80.0, 87.3]** | 70.3% [65.6, 74.7] | 0.46 / 0.71 / 0.85 |

The intervals sit on top of each other, and the contact arm's confidence
quartiles are, if anything, slightly *higher*. Per species: contact detects
at 93.9% for Hooded Crow (31/33) and 77.8% for Northern Raven (35/45);
alarm at 83.3% and 86.7%.

Caveats that keep this honest: the bout unit is an energy burst inside a
recording whose *whole file* the recordist called contact, so some scored
bouts are surely other vocalisations — but the alarm arm carries the
identical dilution, which is what the comparison controls for. And both arms
are European corvids; nothing here measures American Crow contact timbre
directly. The claim is narrower and still the useful one: contact-type
vocalisation does not evade corvid species detection.

## What it changed

- **The funnel has a finder.** Candidate contact bouts can be surfaced from
  detections the pipeline already produces — window captures and scrape
  audio alike — and put in front of Ben's trained ear. No new model, no
  waiting on the embedding assist to *find* candidates; the assist (FUTURE's
  active-learning entry) is still worth having for *diversity*, not for
  existence.
- **It sharpens the 0036 worry.** BirdNET keeps contact calls with high
  confidence, so the corpus's BirdNET-selected training audio almost
  certainly already contains them — sitting under wrong call-type guesses,
  since the head's vocabulary cannot say contact. The "60% alarm" reading on
  new sources stays untrustworthy for exactly this reason.
- **Nothing here needed building.** The measurement used 0013's segmenter
  and the existing worker unchanged — the decision was one afternoon of
  numpy, which is the point of writing it down.
