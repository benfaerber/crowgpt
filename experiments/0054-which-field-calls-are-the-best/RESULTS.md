# 0054 — which field calls are good enough to publish?

## Overview

Ben asked, for the promo site, whether the project could "pick the creme de la creme of crow calls" from his own field recordings. No such ranking existed anywhere in the repo, so this experiment built one: it scored the 57 human-labelled call spans on the 24 starred (kept) captures — the only recordings known to be real field audio rather than seeded archive clips — and produced a shortlist of 8 clips, one per capture, covering every call type. The ranking chooses which clips get listened to; Ben's ear makes the final pick. Along the way it caught two measurement bugs that would each have shipped a bad clip, and discovered that one kept field recording contains three digital dropouts of exactly 3.00 seconds each.

## In depth

### Why these clips and not others

The pool is Ben's own field recordings — not the archive corpus and not the generator — for two hard constraints, neither about quality. The archive corpus is out because some recordings are CC BY-NC-ND and the corpus's derived units are explicitly not redistributable; a public page cannot carry them, and generated clips are trained on them. The generator is out for a second reason: experiment 0053 was mid-flight and blinded, and publishing "the best generated clips" would hand Ben the answer while he was still grading.

The 24 ★ keep captures (all from device 10, Ben's daily phone) have neither problem. The keep flag is the only thing separating a real field recording from seeded archive audio and test uploads, so this is one of the few rankings in the project that is genuinely about crows rather than about the pipeline.

The unit is a labelled span, not a capture. Captures run 14 s to 172 s and are mostly ambience; ranking whole files by SNR picks long quiet recordings containing one distant caw. The `labels` table holds 57 human-marked spans with a call type on each — the only place in the project that says *the crow is here*.

### Numbers

57 human labels on kept captures yielded 44 candidates. Skipped: 8 for call type (`unsure` ×6, `not_a_crow` ×2 — the recordist had already said he could not vouch for them) and 5 for running over 12 s.

| | count |
|---|---|
| clean | 34 |
| clipped | 8 |
| dropout | 2 |

Clean by type: 25 alarm call, 6 begging, 3 call. Clipping is real and confined to captures 102, 103 and 104, all peaking at exactly 0.0 dBFS with clip events recorded — and capture 102 is the top-ranked capture by stored SNR, so an SNR-only ranking would have published a distorted clip first.

### The shortlist

One clip per capture, every call type represented — because 25 of 34 clean candidates are alarm calls and capture 100 alone supplies seven. Experiment 0042 is the reason for the one-per-capture rule: timbre varies 6.2× more between recordings than within one, so two clips from the same capture are nearly the same clip to a listener.

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

Leading run-up is trimmed to 0.25 s ahead of the call; capture 69's best span does not open for 3.15 s, which on a promo page is three seconds of nothing.

### Two measurement mistakes, both caught by an obviously wrong number

Both were the same class of error — an absolute threshold applied to audio — and each would have shipped a bad clip.

1. **The noise floor was measured inside a dropout.** The first version took the 10th percentile of band energy across the whole recording. Capture 100 contains three gaps of exactly 3.00 s (at 19.0, 45.5 and 63.0 seconds), so its floor came out at the numeric floor and its spans scored 156–168 dB SNR — nine clips from one glitched recording took the top nine places. Fixed by excluding digitally silent frames from the floor.
2. **"Dropout" measured as a fraction flagged healthy recordings.** Counting silent samples reported 1.4–2.8% on captures 69, 88 and 154, none of which has a silent run longer than 20 ms — quiet audio crosses zero on almost every cycle. It was excluding capture 69, the best clip in the set. Fixed by measuring the longest contiguous run; afterwards the flag fires on capture 100 and nothing else.

### The finding that outgrew the question

Capture 100's three digital dropouts of exactly 3.00 seconds are not a microphone glitch — identical round durations mean something writing silence in fixed-size units. Its stored `band_snr_db` is 0.0, so `analyzer`'s own quality pass choked on it and nobody noticed, because nothing reads that column looking for zero. This is a kept capture — a real field recording Ben chose to keep — with 11.8% of it missing. Filed in `TODO.txt`.

### What this changed

- A re-derivable "best clips" list now exists (`candidates.json`), with the measurement behind each entry rather than a folder somebody once curated by hand.
- `unsure` and `not_a_crow` labels are treated as unpublishable — the first time those labels have been used for anything.
- Clipping and dropout sort last regardless of SNR; both are defects a listener cannot un-hear, and the top capture by stored SNR is clipped.
- A dropout bug in a kept capture was found, along with the silent tell that `capture_quality.band_snr_db = 0.0` goes unread.

**Not decided here:** which clips actually go on the page. Ben picks from the shortlist by ear — the third time in this project that an automated ranking has ordered arms correctly and located nothing.

**Before anything ships:** the promo bundle is public and these captures carry `location_name`, latitude and longitude, and free-text notes. Publish the audio only; nothing in `candidates.json` should be copied to the page as-is.
