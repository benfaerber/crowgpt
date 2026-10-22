# 0021 — Does the call-type token do anything?

0018 ended with a list of things not done: train a call-type head on bouts, use
it to label the corpus, add a call-type prefix token, retrain the generator, and
ask it for an alarm call. All of that is now built. This asks the only question
it was built for — request a call type, and does that call type arrive?

## How it was measured

Two measurements, and the first is what makes the second mean anything.

A head that cannot classify **real** bouts says nothing about generated ones, and
a confusion matrix from a broken judge looks exactly like a generator ignoring
its conditioning. So the head is scored first on the 198 human-labelled bouts
that fall in the generator's **test** split — seen by neither the head nor the
generator — of which 154 produced a BirdNET embedding. That is the ceiling. Only
then is the same head pointed at 240 generated clips, 60 per requested type.

Forced choice throughout, no confidence threshold. `predict` abstains below 0.60
because a wrong pseudo-label is expensive when labelling 57,000 bouts; here
abstention would hide the answer, and "declined to guess" is not the same finding
as "guessed wrong". Mean confidence was 0.96 on real bouts and 0.91 on generated.

## The judge is real, but only for two of the four classes

154 held-out bouts, 90.3% correct against an 82.5% always-alarm baseline.

```
                alarm call     begging        call        song
  alarm call           124           3           0           0   (n=127)
  begging                6          10           1           2   (n=19)
  call                   0           0           3           0   (n=3)
  song                   1           1           1           2   (n=5)
```

Excellent on alarm (124/127) and genuinely informative on begging — 10 of 19,
against a 12% base rate. But `call` and `song` land on n=3 and n=5. **The
held-out set is too alarm-dominated to validate those two at all**, so any
verdict the head later gives on generated song or call clips is itself
unvalidated. That limit is carried into the conclusion below rather than
papered over.

## The answer: yes, and it degrades exactly with training data

240 clips requested, 219 embedded (21 were too short for BirdNET to segment).

```
                alarm call     begging        call        song
  alarm call            52           1           0           3   (n=56)
  begging               23          28           0           5   (n=56)
  call                  36           6           2           8   (n=52)
  song                  34          12           0           9   (n=55)
```

41.6% of clips came back as the type requested. Chance agreement given these
marginals is 25.5% and an always-alarm judge would score 25.6%, so **the token
is not being ignored** — Cohen's kappa 0.215. The rows are visibly different
from each other, which is the thing a generator ignoring its prefix cannot do.

But the per-class recall is the real result, and it is monotonic in the number
of training bouts of that type:

| requested | train bouts | came back as requested |
|---|---:|---:|
| alarm call | 26,876 | 92.9% |
| begging | 2,349 | 50.0% |
| song | 1,113 | 16.4% |
| call | 272 | 3.8% |

Four classes, four orders of magnitude of data, and the ordering is exact. The
conditioning token works in proportion to how much of that type the model saw.
Roughly 2,000 bouts buys usable control; 1,000 buys a hint; 272 buys nothing.

`call` fails outright — 2 detections in 219 clips. The generator effectively
cannot produce one on request. Note the head is not blind to `call` (3/3 on
held-out), but at n=3 that is not a licence to say confidently *why* it fails,
only that it does.

## Caveats worth keeping

- **`song` and `call` conclusions are soft.** The judge was validated on 5 and 3
  examples. "Song conditioning is weak" is partly "we cannot yet tell."
- **The head was trained on real bouts and applied to generated audio.** That is
  a domain shift. 0020 found no timbre measure that distinguishes generated from
  real, which mitigates it, but does not remove it.
- **21 of 240 clips never embedded**, mostly short ones, so the matrix is over
  clips long enough for BirdNET and is mildly biased toward longer output.
- **Duration says nothing**, as 0020's successor run already suggested: 2.42–2.64 s
  across all four types. Call type does not show up as length, so the earlier
  duration-only result was correctly read as a null rather than a negative.

## What changed

- **Call-type conditioning is established as working**, not merely possible.
  0018 showed the path was open; this shows something came out the other end.
  The generator can be asked for an alarm call or a begging call and will
  usually comply.
- **The binding constraint is now labelled data per class, not the method.**
  Nothing about the architecture, the prefix token, or the pseudo-labelling
  needs revisiting — `begging` at 2,349 bouts proves the mechanism. `song` and
  `call` need more labelled bouts, which means more human labelling of those
  two types specifically, not more compute or more epochs.
- **A cheap rule of thumb for the next conditioning axis** (context chips, for
  instance): budget on the order of a couple of thousand examples per value
  before expecting control, and do not bother shipping a value with a few
  hundred.
- **The held-out anchor should be enlarged before it is trusted further.** Three
  `call` examples cannot validate a judge. Any future claim about `song` or
  `call` conditioning needs that set grown first — which is the same labelling
  work the point above already calls for.

## Re-running

```bash
cd crowgpt && .venv/bin/python \
  ../experiments/0021-does-the-call-type-token-do-anything/run.py
```

About 20 minutes, nearly all of it generating 240 clips one at a time; there is
no KV cache, so generation is the whole cost. `results.json` holds both matrices.
