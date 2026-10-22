# Does training on 46 species help American Crow, or dilute it?

## Overview

A corpus expansion took the training data from 6 bird species to 46 while adding only 446 American Crow recordings, so the target species fell from 71% of the corpus to 47%. Ben's framing was "is it trained on all languages or just english?" — in language models, adding languages can hurt the high-resource one when model capacity is the constraint, or help it through transfer when data is the constraint. Two otherwise-identical models were trained, one on American Crow only and one on all 46 species, and compared in a blind listening test of 50 forced-choice pairs. The answer is a null in both directions: no detectable difference, so the extra 45 species neither hurt nor helped, and future corpus growth can be chosen on other grounds without worrying about the generator.

## In depth

**Method.** Two arms with one difference: `mono` trains on american-crow only (100,216 sequences), `multi` on all 46 species (214,090). Both use the same tokens directory, so the vocabulary is identical at 8,247 tokens and the model shape does not move. Both are scored on the same 4,560 held-out American Crow sequences — the multi arm's unfiltered validation loss would be an average over 46 species and would move for reasons having nothing to do with the bird under test. The listening sitting was 50 forced-choice pairs plus 10 catch trials.

**Result.**

| | |
|---|---|
| P(multi preferred) | **0.42**, CI [0.28, 0.57] |
| side-balanced | 0.44 |
| too close to call | 10 of 50 |
| catch (real vs mono) | **10/10** |

Not resolved, with the point estimate slightly favouring mono. At 50 pairs this design resolves roughly a 14-point difference, so whatever the other 45 species are worth to American Crow, it is less than that — in either direction. The practical reading: the "curse of multilinguality" does not bite here, and neither does transfer. Forty-five extra species were neutral, which is a cheaper answer than either extreme.

**The offline instruments disagreed with each other, and with the ear.** Held back until the sitting was rated, then compared:

| | mono | multi | favours |
|---|---|---|---|
| best val (held-out crow) | 4.5750 | 4.5719 | multi, by 0.003 nats |
| stage-0 churn | 0.793 | 0.820 | multi, 0.027 closer to real's 0.868 |
| forced choice | — | 0.42 | mono, not resolved |

Validation loss moved 0.003 nats, which is nothing — experiment 0023 moved it 0.164 for a listening difference of exactly zero. Churn made a real prediction and it was not confirmed: it put multi meaningfully closer to real audio and the ear did not agree. After experiment 0045, where churn correctly anticipated the delay-pattern null, it is now 1 for 2 as a ranker — which is what a coin looks like. It stays useful as a triage screen for whether a model is grossly wrong; it has not earned the right to rank two plausible models.

**The listening instrument keeps behaving.**

| | this sitting | 0041 | 0045 |
|---|---|---|---|
| left chosen | **0.70** [0.58, 0.82] | 0.65 | 0.66 |
| first-heard chosen | 0.44 [0.30, 0.58] | — | 0.49 |

The left-button bias replicates a third time and is resolved every time; play order is nothing, twice. Ben's 2×2 fix — balancing which side each arm appears on — is vindicated on two independent sittings: the bias is the button, and balancing sides is the control that does the work. The catch set came back 10/10, the cleanest yet.

**What Ben heard that this cannot measure.** He said: *"I think both models are much better than they once were. I think the more data helped."* This sitting cannot say that — it compares two v2 models against each other, and neither is compared against anything trained on the old corpus. The only cross-sitting anchor is the catch set, and experiment 0038 established that absolute rates are not comparable across sittings even when the real anchor holds. Nor does his impression conflict with experiment 0048 (which found loss flat past 50% of the corpus): 0048 measured loss, Ben describes audible quality, and the project has twice measured the two coming apart. That gap defined the next experiment: v1 `model-fair-k8` against v2 `model-mono-v2`, forced choice — cheap, unrun at the time, and testing directly whether the bigger corpus helped.

**What this changed:**

- **Species mix is not a lever.** 46 species against 1 is neutral at 50 pairs. Future corpus growth can be chosen on what the classifier and the context work need, without worrying about diluting the generator.
- **Churn is demoted to triage.** At 1 for 2 against the ear, it can say a model is broken; it cannot rank two that are not.
- **The 2×2 side-balancing design is confirmed twice over** — side bias resolved, order null.
- **The question worth running next is v1 versus v2**, and it exists only because Ben said the models sound better than they used to. (That became experiment 0050.)
