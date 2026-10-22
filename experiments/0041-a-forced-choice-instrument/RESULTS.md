# A forced-choice instrument, validated on a question already answered

## Overview

Experiment 0038 showed that the absolute-rating listening page grades each clip against the company it keeps — the same model moved 33 points between sittings while the real-audio anchor held still. This experiment built a paired forced-choice instrument instead (which of two clips is better) and validated it by including a comparison whose answer was already known and a set of catch trials, alongside the open question of whether the DAC-44 tokenizer beats EnCodec-8 at the generator. The instrument passed both checks and gave a tighter interval on the open question than absolute rating had, so forced choice became the standard for model-versus-model comparisons. It also uncovered a genuine 65% left-side bias in the listener, as large as the model effect under test.

## In depth

### Method

65 pairs in one sitting on 2026-08-03: 40 pairs of the open question (fairk8 vs dac44), 15 of a comparison already settled the night before (fairk8 vs k5-matched, 0.54 vs 0.17 by absolute rating), and 10 catch trials (real vs fairk8). A forced choice has no company to grade against and estimates one quantity, P(A preferred), against a null of exactly 0.5, rather than differencing two noisy rates. Catch trials pair generated against real, which has a known answer and measures nothing about models — Ben's objection to the original design, and the reason they are catch trials rather than an arm; they are excluded from every model comparison.

### Results

Catch (real vs fairk8, 10 pairs): real 9, fairk8 1. P(fairk8) = 0.10, interval excludes 0.5. The listener was engaged and real beats generated, as it must.

Known comparison (fairk8 vs k5-matched, 15 pairs): fairk8 11, k5-matched 4. P(fairk8) = 0.73, interval [0.53, 0.93], excludes 0.5. The instrument reproduces a known answer, which is what licenses reading the open one.

Open question (fairk8 vs dac44, 40 pairs): fairk8 20, dac44 12, and 8 too close to call. Raw P(fairk8) = 0.62; side-balanced, 0.65. The interval marginally includes 0.5, so this remains unresolved — but it is tighter than 0037's attempt and points the other way:

| | 0037 (absolute rating) | 0041 (forced choice) |
|---|---|---|
| favours | dac44, barely | fairk8 |
| interval width | 0.50 | 0.31 |

Combined with 0037's null, the fair summary is that DAC-44 did not beat EnCodec-8 at the generator and may be worse. The 20% too-close rate on this pairing against 0% on the other two is the same finding from the inside: these two are genuinely hard to separate.

### The side bias

Left was chosen on 37 of 57 decided trials — 0.65, interval [0.53, 0.75], excludes 0.5. A real side preference, as large as the model effect under test. Inside the open pairing, fairk8 won 12 of 14 (0.86) when placed on the left and 8 of 18 (0.44) when placed on the right — a 42-point swing on the same model from which button it sat above. Randomising sides only cancels this in expectation: over 32 trials it put fairk8 left 14 times and right 18, so the bias leaked into the raw number and had to be corrected afterwards.

The fix is by construction rather than correction: `PairPage` now balances each arm-pairing exactly — half flipped, half not, per pairing rather than in aggregate, since balancing only the total lets one comparison sit left-heavy while another compensates. Two tests hold it. This was the second time recording a nuisance variable paid for itself: 0040 needed recording ids that Phase 3 never stored, and this needed the side, which existed only because the page was written to record it.

### Caveats

The open question did not resolve; the interval marginally includes 0.5. The result is a validated instrument plus a directional lean, not a settled ranking of the two tokenizers.

### What this changed

- The forced choice is the instrument for model-vs-model comparisons from now on: it reproduced a known answer, resolved the catch set, and gave a tighter interval than absolute rating on the same question.
- Absolute rating keeps one job — how far from real — which forced choice cannot say, and which is the number that says whether the project is going anywhere.
- Never randomise a nuisance variable you can balance; random assignment is what let a 65% side bias reach the estimate.
- Ben reported the task "much easier and less stressful" at 4.4 s a trial against roughly 1.4 s for a single clip — slower per trial, two clips covered, and it removed the effortful part, holding a scale in his head.
- DAC-44 is unlikely to be the answer: two instruments, neither resolving it, both pointing at EnCodec-8 or a tie. The tokenizer route stays closed.
