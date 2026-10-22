# 0049 — Does training on 46 species help American Crow, or dilute it?

**2026-08-05** · 50 forced-choice pairs + 10 catch · **answer: no detectable
difference either way**

## The question

Ben's framing: *"is it trained on all languages or just english?"* The sweep took
the corpus from 6 species to 46 while adding only 446 American Crow recordings,
so American Crow fell from 71% of the corpus to 47%. Multilingual language models
show a "curse of multilinguality" — adding languages hurts the high-resource one
— but **only when capacity binds**. When data binds, transfer runs the other way.

Two arms, one difference: `mono` trains on american-crow only (100,216
sequences), `multi` on all 46 (214,090). Same tokens directory, so the vocabulary
is identical at 8,247 and the model shape does not move. **Both scored on the
same 4,560 held-out American Crow sequences** — the multi arm's unfiltered
validation loss would be an average over 46 species and would move for reasons
having nothing to do with the bird under test.

## Result

| | |
|---|---|
| P(multi preferred) | **0.42**, CI [0.28, 0.57] |
| side-balanced | 0.44 |
| too close to call | 10 of 50 |
| catch (real vs mono) | **10/10** |

**Not resolved, point estimate slightly favouring mono.** At 50 pairs this
resolves roughly a 14-point difference, so whatever the other 45 species are
worth to American Crow, it is less than that — in either direction.

The practical reading: **the curse of multilinguality does not bite here, and
neither does transfer.** Forty-five extra species were neutral. That is a cheaper
answer than either extreme and it means future corpus growth can be chosen on other
grounds — the classifier, the context work — without worrying they will harm the
generator.

## The offline instruments disagreed with each other, and with the ear

Held back until the sitting was rated, then compared:

| | mono | multi | favours |
|---|---|---|---|
| best val (held-out crow) | 4.5750 | 4.5719 | multi, by 0.003 nats |
| stage-0 churn | 0.793 | 0.820 | **multi**, 0.027 closer to real's 0.868 |
| forced choice | — | 0.42 | mono, not resolved |

Validation loss moved 0.003 nats, which is nothing — 0023 moved it 0.164 for a
listening difference of exactly zero.

**Churn made a real prediction and it was not confirmed.** It put multi
meaningfully closer to real audio and the ear did not agree. After 0045, where it
correctly anticipated the delay-pattern null, churn is now **1 for 2** — which is
what a coin looks like. It stays useful as a triage screen for whether a model is
grossly wrong; it has not earned the right to rank two plausible models.

## The instrument keeps behaving

| | this sitting | 0041 | 0045 |
|---|---|---|---|
| left chosen | **0.70** [0.58, 0.82] | 0.65 | 0.66 |
| first-heard chosen | 0.44 [0.30, 0.58] | — | 0.49 |

**Left bias replicates a third time and is resolved every time. Play order is
nothing, twice.** Ben's 2×2 fix has now been vindicated on two independent
sittings: the bias is the button, and balancing sides is the control that does
the work.

The catch set came back 10/10, the cleanest yet.

## What Ben heard that this cannot measure

> *"I think both models are much better than they once were. I think the more
> data helped."*

**This sitting cannot say that.** It compares two v2 models against each other;
neither is compared against anything trained on the old corpus. The only
cross-sitting anchor is the catch set, and 0038 established that absolute rates
are not comparable across sittings even when the real anchor holds.

It also sits against 0048, which found validation loss flat past 50% of the
corpus and concluded more data would not help. **Those two claims are not
actually in conflict**, because 0048 measured loss and Ben is describing audible
quality, and rule three of this project is that the two come apart — twice
measured. A corpus 1.6× larger could leave loss flat and still sound better.

That is a real, cheap, unrun experiment and it is now the most interesting one
available: **v1 `model-fair-k8` against v2 `model-mono-v2`, forced choice.** Both
checkpoints exist. Different vocabularies do not matter when the comparison is
audio. It directly tests whether the bigger corpus helped, which is the question the
whole week has been circling.

## What this changed

- **Species mix is not a lever.** 46 against 1 is neutral at 50 pairs. Stop
  worrying about dilution; choose future corpus growth on what the classifier and the
  context work need.
- **Churn is demoted to triage.** 1 for 2 against the ear. It can say a model is
  broken; it cannot rank two that are not.
- **The 2×2 is confirmed twice over** — side biased and resolved, order null.
- **The question worth running next is v1 versus v2**, and it exists only because
  Ben said the models sound better than they used to.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0049-does-training-on-46-species-help-american-crow/run.py
```

Two arms at ~62 min each, then evaluation. Session in
`crowgpt/results/listening/multilingual-0049/`.
