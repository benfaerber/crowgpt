# Is any codec actually transparent?

## Overview

The project's tokenizer choice rested on a rating-task claim that DAC-24 at 24 codebooks is indistinguishable from raw audio, and the listener had begun to doubt both the codec and his own grading criterion. This experiment built an ABX discrimination test — which of two renderings matches a reference — because ABX has no good/bad criterion to misplace and chance is exactly 50%. Across two readable sittings the listener could not tell DAC-24 from raw above chance (a pooled point estimate of exactly 0.500 over 140 trials), so DAC-24 was adopted; strict transparency was left unproven because the test cannot bound discriminability tighter than about 60% at this trial count. The intended positive control, EnCodec at 6 kbps, also failed to resolve, which turned out to be a design error: it had been chosen as "known audible" on the say-so of the very rating instrument the experiment existed to doubt.

## In depth

### Why

Experiment 0034 concluded DAC-24 at 24 codebooks is "blind-indistinguishable from raw (0.88 vs 0.92)". That sentence set the ceiling arithmetic 0037 used and is why no tokenizer work had been costed since. On 2026-08-02 Ben contradicted it by ear ("DAC-24 is bad too — all the codecs are bad", "the best of the worst") and, more seriously, described his own grading slipping: "I marked as good knowing it was AI but it was a good AI call" — a criterion of "good for an AI clip" inflates every arm.

Checks over the saved rating sessions could not settle it. Trial-to-trial contrast matched on arm was −0.012 (nothing); first half vs second half of a sitting was 0.670 → 0.647 (nothing); the raw anchor correlated with the mean of the other arms at r = +0.469 over seven sittings (suggestive, unresolved at n = 7). All three tests look for a criterion changing, and a criterion that was stable but anchored in the wrong place is invisible to every one of them. A different instrument was needed.

### Method

ABX: each trial is one bout rendered two ways; X is the same source as one of A or B, and the answer is which. 120 trials: 90 on dac24_24 (the question) and 30 on encodec8 as a positive control — a difference believed already audible, so that a control failure would mark the sitting itself as broken. Protections included: no waveforms shown; A/B sides balanced by construction within each arm (45/45 and 15/15 — independent coin flips in the first build would have let a listener pressing "b" every time score 0.600, exactly the p = 0.049 threshold on the control arm); X points at a side rather than copying it; identical renderings raise at build time; every clip peak-normalised; unlimited replay; 120 bouts never before played to Ben, selected by reading bout ids out of all ten saved sessions (492 spent so far).

Power, written before the sitting: at 90 trials the 95% interval is ±10.3 points at its widest; chance is rejected at 54/90 = 60.0% (p = 0.036); the control resolves at 20/30 = 66.7% (p = 0.049). The design cannot prove transparency — on a perfect 45/90 the upper bound is still 60.1% — so the strongest available statement is "discriminability is at most about 60%". A real ±10 equivalence claim would need roughly 200 trials per arm.

There is no generated audio anywhere in this experiment: all 240 renderings across 120 trials derive from real recordings, and no model or checkpoint is loaded in `run.py`.

A pool caveat found mid-sitting: this sitting's 120 bouts put more of their energy in the corvid band than the 492 already heard (800–4000 Hz share 0.710 vs 0.605, difference +0.105 [+0.051, +0.158], resolved; duration and crest factor not resolved). The plausible direction is toward a harder test — background noise masks codec artefacts — so an indistinguishability result on this cleaner pool is if anything stronger evidence.

The page must be sat in Chrome; Firefox plays no audio, most likely due to its handling of large `data:` URI media (240 embedded WAVs, 32 MB). Not diagnosed, and not a confound: within a sitting every arm plays through the same chain.

### Attempt 1, 2026-08-03 — void

| arm | correct | rate | 95% CI | p(chance) |
|---|---|---|---|---|
| dac24_24 | 23 / 50 | 0.460 | [0.330, 0.596] | 0.760 |
| encodec8 (control) | 11 / 20 | 0.550 | [0.342, 0.742] | 0.412 |

The control did not resolve, so by the pre-registered rule the DAC arm is unreadable. Three faults were found by the failure: the page died at trial 72 because every clip got its own retained `Audio` element (360 at 120 trials; fixed to one shared element); the sitting spanned 10 h 41 m of which only 7.4 minutes were decisions (fixed by recording `answered_at` per trial and warning in `analyse.py`); and everything was rendered at 16 kHz, deleting all content above 8 kHz — exactly where 0036 had measured both codecs altering the band above 6 kHz (EnCodec −0.66 dB, DAC −1.42 dB in call regions). Fixed to native 24 kHz. The audio itself was verified correct: log-mel distance between the sides was 0.664 for EnCodec-8 and 0.548 for DAC-24, so the arms were the right way round (a raw sample-wise RMS comparison says the opposite and is wrong — DAC's round-trip carries a median 5-sample time offset).

### Attempt 2, 2026-08-03 — clean sitting, control failed again

120 of 120 answered in 12 m 37 s in Chrome.

| arm | correct | rate | 95% CI | p(chance) |
|---|---|---|---|---|
| dac24_24 | 47 / 90 | 0.522 | [0.420, 0.622] | 0.376 |
| encodec8 (control) | 17 / 30 | 0.567 | [0.392, 0.726] | 0.292 |

Pooled with attempt 1 the control is 28/50 = 0.560, p = 0.24 — still chance, across two sittings and two browsers, against Ben's own impression that "Encodec8 was pretty obvious most of the time". The control had been chosen circularly: EnCodec-8 was picked as "known audible" from 0028's rating gap (0.45 against raw's 0.85), a number produced by the rating task this experiment exists to doubt. Measured independently by log-mel distance from raw over 24 held-out bouts, all the codecs sit in one narrow band (DAC-24 0.617, EnCodec 6 kbps 0.716, EnCodec 1.5 kbps 0.791) while a genuine ruination — a 2 kHz lowpass — sits at 5.522, seven times further out. "The control failed" is therefore equally consistent with every codec being far closer to transparent than the rating tasks implied.

One real signal: effort helps. Trials with one play per clip scored 0.506 (DAC) and 0.519 (EnCodec); trials with four or more plays scored 0.615 and 3/3. At 6.3 seconds a trial for three clips, the task was being answered faster than it supports.

### Attempt 3 — built, not sat

A third page adds a 2 kHz lowpass anchor (20 trials) whose only property is that it must be discriminable, with dac24_24 at 60 trials and encodec8 at 40 — now a question rather than a control. Stopped by decision on 2026-08-03, on Ben's call: "Can you just do Dac24? It sounds better to my ears I don't need more evidence." The page is on disk and re-runnable.

### Closed: DAC-24 adopted on the ear, transparency left unproven

Established: DAC-24 at 24 codebooks is transparent to within 8 points on a validated instrument, and 0034 was right — the listener's impression ("I could only ever tell based on a minor intuition, most were guesses") agrees with a point estimate of exactly 0.500 over 140 trials. Open: EnCodec at 6 kbps is not resolvable either (28/50), against a 40-point rating gap and the listener's "pretty obvious", which puts the founding unblinded "scratchy and worse" claim from 0024 Part 3 in need of a blind re-test it has never had.

### What this changed

- The tokenizer question is closed by decision, not by proof, and the distinction is recorded rather than smoothed over.
- `ABXPage` exists and is tested, including a node harness that runs the rendered page's own JavaScript; three browser faults still reached Ben because every Python-side test passed on pages that made no sound.
- A control must be validated by something other than the instrument it is controlling. Two sittings were spent before that circularity was noticed; the lowpass anchor is the fix and is in `run.py`.
- Rating-task equivalence claims across 0030–0037 stay flagged provisional. This experiment did not clear them; it ran out of reasons to keep trying.
