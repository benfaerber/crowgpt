# 0018 — Can CrowGPT be conditioned on call type?

## Overview

The project wants its crow-call generator to produce a *requested* kind of call — an alarm call, a begging call — which requires labelled examples of each type. An earlier experiment (0013) had declared this out of reach because only 67.7 seconds of human-labelled audio existed; vendoring the crow-tools labels brought in roughly forty times that, so the blocker was worth re-testing. The answer is yes, with a step in between: the classifier head that ships with crow-tools does not transfer to this project's audio units and scored worse than always guessing "alarm call", but a fresh classifier trained directly on those units matched the shipped head's quality from only 805 examples. The path to conditioning is open — train a head on bouts, use it to label the rest of the corpus, then condition the generator — though this experiment establishes only that the path exists, not the destination.

## In depth

Run on 2026-07-31 over 1,091 human-labelled bouts, 805 usable, with recording-grouped cross-validation. Three things had to be true: the labels must join onto crowgpt's bouts; there must be enough of them; and a bout must actually *have* a call type.

### A. The join works, and yields less than hoped

86% of crow-tools' labelled recordings are in the corpus, but crow-tools labelled about two seconds per recording while each recording yields roughly fifteen bouts, so most bouts fall outside every label span.

| | |
|---|---|
| American Crow bouts in the corpus | 57,479 |
| bouts from labelled recordings | 15,396 |
| **bouts overlapping a label** | **1,091** |
| of those, single-label | 1,001 |
| alarm / begging / call / song | 725 / 121 / 88 / 67 |

1,091 is thin for conditioning an 18M-parameter model directly, and two thirds of it is alarm call.

### B. The shipped head cannot pseudo-label them

The obvious fix was to label all 57,479 bouts with the American Crow call-type head that already ships — the one 0013 named good enough — keeping the human labels as an untouched test set. That fails. Against the human labels, on single-label bouts, the head's top class is right 56% of the time; always guessing "alarm call" scores 69%.

| human label | n | what the head said |
|---|---|---|
| alarm call | 549 | alarm 419, begging 58, call 39, song 33 |
| begging | 103 | **alarm 71**, begging 17, song 11, call 4 |
| call | 84 | **alarm 61**, song 9, begging 8, call 6 |
| song | 57 | **alarm 41**, begging 9, song 4, call 3 |

It answers "alarm call" to almost everything: 592 of 793 predictions. A head with 0.904–0.975 AUC on its own data is worse than a constant on ours.

### C. But a head trained on bouts works fine

The question then became whether bouts carry call type at all — a bout is 2.4 s holding about 3.8 calls, and might simply not be a thing with one type. They do. A plain logistic regression on BirdNET embeddings of bouts, with five-fold recording-grouped cross-validation so no recording appears on both sides:

| class | n | one-vs-rest AUC |
|---|---|---|
| alarm call | 622 | **0.951** |
| begging | 105 | **0.937** |
| call | 34 | 0.994 |
| song | 44 | **0.918** |
| *(shipped head, on crow-tools 1 s segments)* | | *0.904 – 0.975* |

That matches the shipped head's numbers, on 805 examples instead of 2,654. The unit is not the problem and the labels are not too few — the shipped head simply does not transfer. Its training segments are about 1 s, single-call, differently preprocessed; a bout is longer, holds several calls, and is peak-normalised. That is domain shift, not a failure of the idea.

### Caveats

`call` at n=34 with an AUC of 0.994 should be read with suspicion; the other three classes are on enough examples to believe. The labelled bouts come from the vendored crow-tools labels over corpus recordings, not from field captures of the Poe family, so these numbers describe the pipeline's labelling capability rather than any specific birds.

### What changed

- **0013's blocker is lifted for American Crow.** "Not from human labels: 67.7 seconds, 5 isolated calls" was true of the field corpus and is not true of the vendored crow-tools labels.
- **A head must be retrained per unit, not reused across units.** The shipped head's AUC is a fact about 1-second segments; nothing warned it would degrade below a constant classifier on 2.4-second bouts, and nothing would have caught it except comparing against human labels on the new unit.
- **Pseudo-labelling is viable, with the human labels held out** as the only honest test set — a head trained on bouts, judged against people, never against itself.

Not done here: training the bout head on all 805 examples, labelling the corpus, adding a call-type prefix token, retraining the generator, and asking it for an alarm call. That follow-through is experiment 0021.
