# Does the delay pattern help?

## Overview

After tokenizer changes, capacity, sequence length and architecture had all failed to improve generated crow audio, one modelling idea remained untried: changing the token layout from flat interleaving to MusicGen's delay pattern, which MusicGen reports as the fix for flat interleaving's weaknesses. A model was trained matched to the incumbent in everything but layout and judged by blinded forced choice. The result was a null — a coin flip at P(delay preferred) = 0.53 with 60 pairs — closing the last untried modelling route. The sitting also settled a standing methodological question: the listener's known selection bias is a left-button bias (0.66, resolved, replicating 0041's 0.65), not a preference for whichever clip plays first (0.49, no effect).

## In depth

### The question

Every other route was closed: four tokenizer configurations moved nothing (0028, 0032–0037), capacity was ruled out twice at two sequence lengths (0023, 0038), shortening the sequence hurt badly (0038), and the extender died on DAC's near-white fine stages (0035). What had never been varied was the objective — every model in the project predicts the next token over a flat interleaved stream. Flat was suspect for a specific reason: at position (t, k) the model predicts codebook k of frame t from codebooks 0..k−1 of the same frame plus everything before, so fine stages hang off a coarse prediction made three tokens earlier and errors compound inside a frame — a plausible shape for 0027's "right structure, wrong texture". MusicGen reports flat interleaving as the worst of its four layouts and the delay pattern as the fix.

The delay model was matched to `model-fair-k8` exactly — d384/L8/H6, effective batch 18, dropout 0, 30,000 steps, same corpus, same codec. Only the token layout moved.

### Results

60 forced-choice pairs plus 10 catch trials, sat 2026-08-04/05.

| | |
|---|---|
| P(delay preferred) | 0.53, CI [0.39, 0.67] |
| side-balanced | 0.53 |
| too close to call | 11 of 60 |

Not resolved, and the point estimate is a coin flip. At 60 pairs this design resolves roughly a 13-point difference, so the delay pattern is worth less than that. The catch set came in at 8/10 for real — wider than previous sittings but in the right direction.

Combined with the closed routes above, no change to the tokenizer, the capacity, the sequence length, the architecture or the token layout has moved generated audio: five independent routes, one conclusion.

### The offline screen predicted it

Experiment 0046's churn metric, measured before the sitting, put the delay model at stage-0 churn 0.780 against `fair-k8`'s 0.801 and real audio's 0.868 — stickier, not less. The ear then found no difference at all. The screen called the direction right (not an improvement) while overstating the size (it suggested worse; the ear said same). That is the first time an offline instrument in this project anticipated a listening result rather than contradicting one, and it cost two minutes against the sitting's hour. Worth keeping, worth not over-trusting.

### Ben's fix answered its own question immediately

He proposed playing a random side first, to separate a left-button bias from a first-heard bias. Until this experiment the left clip always played first, so the two were the same measurement wearing two names. Balanced as a 2×2, they separate cleanly:

| | rate | 95% CI | |
|---|---|---|---|
| left chosen | 0.66 | [0.54, 0.78] | resolved |
| first-heard chosen | 0.49 | [0.37, 0.63] | not resolved |

The bias is the button, not the order. Left replicates almost exactly across sittings (0.65 in experiment 0041, 0.66 here), and hearing a clip first is worth nothing — 0.49 is as close to no effect as 59 trials can show. The balancing that matters is of sides; randomising play order was harmless and was the only way to learn this, but it does no bias-control work.

### What this changed

- The modelling route is exhausted: five ideas, five nulls. Anything further on the generator needs a genuinely new class of idea.
- One cheap thing remains before pivoting: experiment 0047 found a repetition penalty of 1.05 lands on real audio's stage-0 churn (0.866 against the 0.868 target) where the current default sits 0.049 short — a sampling change needing no training, never heard. One sitting, not one night.
- The honest next move after that is the context work: experiment 0040 showed Phase 3's "call types do not cluster" was measured in a space where the microphone outranks the species, so the question the project exists to answer has never been properly asked.
- The offline screen earned a place — triage, never decide.
- Left-button bias is confirmed and order bias is refuted, so future pages need side balancing and nothing else.
