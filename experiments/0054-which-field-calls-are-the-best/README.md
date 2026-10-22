# 0054 — which field calls are good enough to publish?

**Question.** Ben, for the promo site: *"can we pick the creme de la creme of crow
calls."* There was no such list anywhere in the repo — nothing ranks individual
clips by quality — so this builds one and writes down how, because "the best
clips" is otherwise a judgement nobody can re-derive.

**Status: 8 clips shortlisted, waiting on Ben's ear.** The ranking chooses which
clips get listened to. It does not decide.

## Why these clips and not others

**Ben's own field recordings, not the corpus and not the generator.** Two hard
constraints, neither about quality:

- **The archive corpus is out.** Some of those recordings are CC BY-NC-**ND** and the
  corpus's derived units are explicitly not redistributable. A public page cannot
  carry them, and generated clips are trained on them.
- **The generator is out for a second reason:** 0053 is mid-flight and blinded.
  Publishing "the best generated clips" while Ben is grading channel-000 against
  channel-081 would hand him the answer.

The 24 **★ keep** captures have neither problem. All are from device 10, his daily
phone, and the keep flag is the only thing separating a real field recording from
seeded archive audio and test uploads.

**The unit is a labelled span, not a capture.** Those captures run 14 s to 172 s
and most of each is ambience — the crow is a few seconds somewhere inside. Ranking
captures by whole-file SNR picks long quiet recordings containing one distant caw.
The `labels` table holds **57 human-marked spans** with a call type on each, which
is the only place in this project that says *the crow is here*.

## Numbers

57 human labels on kept captures → 44 candidates. Skipped: 8 for call type
(`unsure` ×6, `not_a_crow` ×2 — the recordist already said he could not vouch for
them) and 5 for running over 12 s.

| | count |
|---|---|
| clean | **34** |
| clipped | 8 |
| dropout | 2 |

Clean by type: 25 alarm call, 6 begging, 3 call. Clipping is real and confined to
captures **102, 103, 104**, all peaking at exactly 0.0 dBFS with clip events
recorded — and capture 102 is the **top-ranked capture by stored SNR**, so an
SNR-only ranking would have published a distorted clip first.

### The shortlist

One per capture and every call type represented, because 25 of 34 clean candidates
are alarm calls and capture 100 supplies seven. 0042 is the reason to care: timbre
varies **6.2× more between recordings than within one**, so two clips from the same
capture are nearly the same clip to a listener.

| | type | capture | secs | span SNR | trimmed | what it is |
|---|---|---|---|---|---|---|
| 1 | call | 69 | 6.8 | 23.9 | 2.9 s | Ben walk under crow tree and feed |
| 2 | alarm call | 115 | 3.5 | 13.7 | 0.2 s | Crows scatter from car then land |
| 3 | alarm call | 114 | 3.7 | 13.6 | — | 5 crows in shaded flower bed |
| 4 | begging | 116 | 3.7 | 13.2 | 0.1 s | Baby caws from north |
| 5 | alarm call | 88 | 3.1 | 13.2 | 0.6 s | Crow alarms on tall building |
| 6 | call | 100 | 12.3 | 10.4 | 0.1 s | Lawnmower + 4 crows on ground |
| 7 | alarm call | 155 | 3.4 | 9.4 | — | New crows |
| 8 | alarm call | 113 | 6.3 | 9.3 | — | 5 crows some on ground some in tree |

Leading run-up is trimmed to 0.25 s ahead of the call. Capture 69's best span does
not open for 3.15 s, which on a promo page is three seconds of nothing.

## Two measurement mistakes, both caught by a number that was obviously wrong

Recorded because each would have shipped a bad clip, and because both were the
same class of error — an absolute threshold applied to audio.

**The noise floor was measured inside a dropout.** The first version took the 10th
percentile of band energy across the whole recording. Capture 100 contains three
gaps of **exactly 3.00 s** at 19.0, 45.5 and 63.0 seconds, so its floor came out at
the numeric floor and its spans scored **156–168 dB SNR** — nine clips from one
glitched recording took the top nine places. Fixed by excluding digitally silent
frames from the floor.

**Then "dropout" was measured as a fraction and flagged healthy recordings.**
Counting silent *samples* reported 1.4–2.8% on captures 69, 88 and 154, none of
which has a silent run longer than 20 ms — quiet audio crosses zero on almost every
cycle and those samples fall below any absolute floor. It was excluding capture
69, which is the best clip in the set. Fixed by measuring the longest contiguous
**run**: after that, the dropout flag fires on capture 100 and nothing else.

## The finding that outgrew the question

**Capture 100 has three digital dropouts of exactly 3.00 seconds**, at 19.0, 45.5
and 63.0 s. Three gaps of an identical, round duration is not a microphone
glitch — it is something writing silence in fixed-size units. Its stored
`band_snr_db` is **0.0**, so `analyzer`'s own quality pass choked on it and nobody
noticed, because nothing reads that column looking for zero.

That is worth a look on its own: it is a kept capture, meaning a real field
recording Ben chose to keep, and 11.8% of it is missing. Filed in `TODO.txt`.

## What this changed

- There is now a re-derivable "best clips" list, `candidates.json`, with the
  measurement behind each one rather than a folder somebody once curated by hand.
- **`unsure` and `not_a_crow` labels are treated as unpublishable**, which is the
  first time those labels have been used for anything.
- Clipping and dropout **sort last regardless of SNR**. Both are defects a
  listener cannot un-hear, and the top capture by stored SNR is clipped.
- A dropout bug in a kept capture was found, and the fact that
  `capture_quality.band_snr_db = 0.0` is a silent tell nobody was reading.

**Not decided here:** which clips actually go on the page. Ben picks from the
shortlist by ear — the third time in this project that an automated ranking has
ordered arms correctly and located nothing.

**Before anything ships:** the promo bundle is public and these captures carry
`location_name`, latitude and longitude, and free-text notes. Publish the audio
only. Nothing in `candidates.json` should be copied to the page as-is.
