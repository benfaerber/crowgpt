# Did the bigger corpus actually help, by ear?

## Overview

After a large corpus expansion, Ben's impression was that the crow-call generator sounded better than it used to: "I think both models are much better than they once were. I think the more data helped." Earlier experiments could not test that impression — they either compared the wrong pair of models or measured training loss rather than sound. This one put the old model (v1, trained before the expansion) directly against the new one (v2) in a blind listening test of 50 forced-choice pairs. The answer is a dead heat: preference for v2 came out at 0.51, as close to no difference as fifty pairs can produce. The corpus had grown 57% overall but only 4% for American Crow, the species being generated, so the null was the honest expectation, and "more data helped" is retired before it could become project folklore.

## In depth

**Why run it despite experiment 0048.** 0048 found validation loss flat past 50% of the corpus and concluded more data would not help — but that measured loss, this measures audible quality, and rule three of this project is that the two come apart. Experiment 0049 could not answer the question either, since it compared two v2 models against each other, and experiment 0038 established that absolute rates are not comparable across sittings even when the real anchor holds.

**Result.**

| | |
|---|---|
| P(v2 preferred) | **0.51**, CI [0.36, 0.67] |
| side-balanced | 0.51 |
| too close to call | 5 of 50 |
| catch (real vs v1) | **10/10** |

A coin flip. The run cost about twenty minutes with no training, since both checkpoints already existed.

**The corpus grew much less than it looks, for this bird.**

| | v1 | v2 | |
|---|---|---|---|
| **american-crow** | 57,479 bouts | 59,654 | **+4%** |
| whole corpus | 81,389 | 127,553 | +57% |

Only 446 of the 10,637 new recordings were American Crow — the archive's corvid holdings skew heavily European, and hooded crows, ravens and jackdaws outnumbered American Crows eight to one in what came back. So this was very nearly "6 species against 46 at the same American Crow", which experiment 0049 had already answered as neutral. Ben's impression is most likely contrast, the effect experiment 0038 caught: recent sittings have had better company, and a memory that includes the extender at 0/24 and the k5 arms at 0.17 makes two decent models feel like an improvement without either having changed.

**His other observation, tested on his own ratings.** Ben also said: *"Looking at waveform it seems to sound best when it has pulses for caws."* The waveform is only revealed after a trial is answered, so this is an observation about what correlates rather than something that drove the choices — which is what makes it testable rather than circular. `PairPage` records each clip's duration, so "more pulses" has a proxy in every session on disk. Across every pairwise trial ever run where the two clips differ in length by more than 0.05 s:

| | longer clip chosen | 95% CI | |
|---|---|---|---|
| all sittings (n=207) | **0.47** | [0.40, 0.54] | not resolved |
| this sitting (n=41) | 0.37 | [0.22, 0.51] | not resolved |

Length does not predict the winner, and if anything the shorter clip wins slightly — consistent with experiment 0026, which found density does not drive ratings, now confirmed on a second instrument and a much larger sample. The honest caveat: duration is a loose proxy for pulse count. A 2-second clip with three crisp caws and a 2-second clip with one smeared one are the same length, and Ben is claiming they are not the same quality. Testing the claim properly needs unit counts per clip — `Segmenter` already produces them, and `PairPage` should record them alongside duration.

**The instrument, fourth reading.**

| | 0041 | 0045 | 0049 | 0050 |
|---|---|---|---|---|
| left chosen | 0.65 | 0.66 | 0.70 | **0.60** |
| resolved? | yes | yes | yes | **no** |
| first-heard | — | 0.49 | 0.44 | 0.53 |

The left-button bias did not resolve for the first time, and the point estimate has come down. Three readings above 0.65 and one at 0.60 is not evidence it has gone — the interval still sits mostly above 0.5 — but it is worth watching rather than treating as a constant. Play order remains nothing on its third independent measurement. Catch was 10/10, the third perfect set running.

**What this changed:**

- **The corpus growth did not help the generator**, measured rather than assumed. On these numbers it was never going to: +4% of the species being generated.
- **"More data helped" is retired as folklore** before it became a premise. Experiment 0048 said it from loss, this says it from ears, and they now agree.
- **Corpus growth aimed at the generator would have to target American Crow specifically**, and the archive does not have much more of it — which points at field recording, Ben's own microphone, rather than archives.
- **Density is not the tell, on a second instrument** — experiment 0026 found it, this confirms it at n=207 across every pairwise sitting.
- **`PairPage` should record unit counts**, so the next observation of this shape can be tested directly instead of through a proxy.
