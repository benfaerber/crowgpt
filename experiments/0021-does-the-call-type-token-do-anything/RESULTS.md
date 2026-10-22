# 0021 — Does the call-type token do anything?

## Overview

Experiment 0018 established that a call-type classifier could be trained on this project's audio units and used to label the corpus; everything on that list was then built — the classifier, the pseudo-labels, a call-type prefix token, a retrained generator. This experiment asked the only question all of that was built for: request a call type from the generator, and does that type actually come out? The answer is yes, and the degree of control tracks training data exactly — requests for "alarm call" (26,876 training bouts) came back correct 92.9% of the time, "begging" (2,349 bouts) 50.0%, "song" (1,113 bouts) 16.4%, and "call" (272 bouts) 3.8%. The conditioning mechanism works; the binding constraint is now labelled examples per class, not the method.

## In depth

### How it was measured

Two measurements, and the first is what makes the second mean anything. A judge that cannot classify *real* bouts says nothing about generated ones, and a confusion matrix from a broken judge looks exactly like a generator ignoring its conditioning. So the classifier head was scored first on the 198 human-labelled bouts falling in the generator's test split — seen by neither the head nor the generator — of which 154 produced a BirdNET embedding. That is the ceiling. Only then was the same head pointed at 240 generated clips, 60 per requested type.

Forced choice throughout, no confidence threshold. The production `predict` path abstains below 0.60 because a wrong pseudo-label is expensive when labelling 57,000 bouts; here abstention would hide the answer, and "declined to guess" is not the same finding as "guessed wrong". Mean confidence was 0.96 on real bouts and 0.91 on generated ones.

### The judge is real, but only for two of the four classes

On 154 held-out bouts, the head is 90.3% correct against an 82.5% always-alarm baseline.

```
                alarm call     begging        call        song
  alarm call           124           3           0           0   (n=127)
  begging                6          10           1           2   (n=19)
  call                   0           0           3           0   (n=3)
  song                   1           1           1           2   (n=5)
```

Excellent on alarm (124/127) and genuinely informative on begging — 10 of 19 against a 12% base rate. But `call` and `song` land on n=3 and n=5: the held-out set is too alarm-dominated to validate those two classes at all, so any verdict the head gives on generated song or call clips is itself unvalidated. That limit is carried into the conclusion rather than papered over.

### The answer: yes, and it degrades exactly with training data

Of 240 requested clips, 219 embedded (21 were too short for BirdNET to segment).

```
                alarm call     begging        call        song
  alarm call            52           1           0           3   (n=56)
  begging               23          28           0           5   (n=56)
  call                  36           6           2           8   (n=52)
  song                  34          12           0           9   (n=55)
```

41.6% of clips came back as the requested type. Chance agreement given these marginals is 25.5% and an always-alarm judge would score 25.6%, so the token is not being ignored — Cohen's kappa is 0.215, and the rows are visibly different from each other, which a generator ignoring its prefix cannot produce.

The per-class recall is the real result, and it is monotonic in training bouts of that type:

| requested | train bouts | came back as requested |
|---|---:|---:|
| alarm call | 26,876 | 92.9% |
| begging | 2,349 | 50.0% |
| song | 1,113 | 16.4% |
| call | 272 | 3.8% |

Four classes, four orders of magnitude of data, and the ordering is exact. Roughly 2,000 bouts buys usable control; 1,000 buys a hint; 272 buys nothing. `call` fails outright — 2 detections in 219 clips; the generator effectively cannot produce one on request. The head is not blind to `call` (3/3 on held-out), but at n=3 that is not a licence to say confidently why it fails, only that it does.

### Caveats

- **`song` and `call` conclusions are soft.** The judge was validated on 5 and 3 examples respectively; "song conditioning is weak" is partly "we cannot yet tell".
- **The head was trained on real bouts and applied to generated audio** — a domain shift. Experiment 0020 found no timbre measure distinguishing generated from real, which mitigates but does not remove it.
- **21 of 240 clips never embedded**, mostly short ones, so the matrix is over clips long enough for BirdNET and mildly biased toward longer output.
- **Duration says nothing**: 2.42–2.64 s across all four types. Call type does not show up as length, so the earlier duration-only result was correctly read as a null rather than a negative.
- The training bouts are pseudo-labelled corpus audio, dominated by archive recordings; these numbers describe the pipeline's conditioning behaviour, not the calls of any particular birds.

### What changed

- **Call-type conditioning is established as working**, not merely possible. 0018 showed the path was open; this shows something came out the other end. The generator can be asked for an alarm call or a begging call and will usually comply.
- **The binding constraint is now labelled data per class, not the method.** `begging` at 2,349 bouts proves the mechanism; `song` and `call` need more human labelling of those two types specifically, not more compute or more epochs.
- **A cheap rule of thumb for the next conditioning axis** (context chips, for instance): budget on the order of a couple of thousand examples per value before expecting control, and do not bother shipping a value with a few hundred.
- **The held-out anchor should be enlarged before it is trusted further.** Three `call` examples cannot validate a judge; any future claim about `song` or `call` conditioning needs that set grown first — the same labelling work the previous point calls for.
