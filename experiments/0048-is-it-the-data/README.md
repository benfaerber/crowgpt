# 0048 — Is it the data?

**2026-08-04/05** · four arms, identical recipe, only the corpus varies ·
**answer: no. More data will not help, and my diagnosis was wrong.**

## The claim this was built to test

After five modelling nulls I argued the corpus was the binding constraint, from
tokens-per-parameter: 74M unique tokens (148M with augmentation) against the
~438M a 21.9M-parameter model wants by Chinchilla — 17% of it. That reading
explained everything at once. It was also checkable in three training runs, which
is the only reason it is now known to be false.

## Result

Same recipe throughout — d384/L8/H6, effective batch 18, dropout 0, 30,000 steps,
EnCodec 8 codebooks — subset **by recording group**, with the validation split
never subset so the losses are comparable.

| data | groups | tokens | best val | gain over previous | stage-0 churn |
|---|---|---|---|---|---|
| 12.5% | 1,205 | 18M | 4.9042 | — | 0.796 |
| 25% | 2,410 | 37M | 4.6814 | **+0.2228** | 0.824 |
| 50% | 4,820 | 73M | 4.6047 | **+0.0767** | 0.791 |
| 100% | 9,640 | 148M | 4.5874 | **+0.0173** | 0.819 |

**Each doubling buys about a third of what the previous one did.** Extrapolating
that ratio, *every remaining recording in the world* is worth roughly +0.026
nats, and the next doubling about +0.017.

**Put that next to 0023: a 0.164-nat improvement produced a listening difference
of exactly zero.** So doubling the corpus buys a change an order of magnitude
smaller than one already measured to be inaudible.

Churn agrees and is flat — 0.796, 0.824, 0.791, 0.819 against real audio's 0.868,
with no trend across an eightfold change in data. The "crow plus modem" defect
does not improve with more corpus either.

### The train/val gaps show where the transition happens

| data | final gap | stopped at |
|---|---|---|
| 12.5% | **+0.5977** | 18,000 (early) |
| 25% | +0.1302 | 30,000 |
| 50% | **+0.0160** | 30,000 |
| 100% | +0.0482 | 30,000 |

At an eighth of the corpus the model memorises hard and early-stops. **By half,
the gap is 0.016 — it is not overfitting and not memorising; it simply cannot do
better.** That is the signature of a model at the limit of what the objective
extracts, not one starved of examples.

## What I got wrong, and why

Chinchilla is a **compute-optimal allocation** result for language models: given a
fixed budget, how should you split it between parameters and tokens. It is not a
claim that a model below that ratio is starved in a way more data repairs. I read
a ratio as a diagnosis and it is not one.

The evidence against it was already on disk before I ran this. 0023 and 0038 both
found capacity not converting to audible quality, and a genuinely data-starved
model is one where capacity *does* convert once data is added — the two findings
were pointing away from data starvation the whole time.

Three training runs was the right price to find out. The wrong price was the two
days of modelling variants that came first.

## What this leaves

Every axis has now been measured and none of them moves generated audio:

| lever | verdict |
|---|---|
| tokenizer | four configurations, no movement (0028, 0032–0037) |
| capacity | ruled out twice, two sizes, two sequence lengths (0023, 0038) |
| sequence length | shortening hurt badly (0038) |
| architecture | extender dead (0035), delay pattern null (0045) |
| sampling | churn reachable, audibility unresolved (0044, 0046, 0047) |
| **data** | **flat past 50% (this)** |

The model's validation loss floor is ~4.59 nats — 6.62 bits per token against the
codec's 8.98-bit marginal, so it recovers 2.36 bits and neither more data nor
more parameters move that. The most economical reading is that **it is at the
conditional entropy of this token stream**: given this tokenizer and this
objective, the next token genuinely is that uncertain, and no model of any size
trained on any amount of this corpus will do better.

That is not a claim the *audio* cannot be improved. It is a claim that
next-token cross-entropy over RVQ acoustic tokens has given what it has to give
at this scale, and the systems that make this work — MusicGen at 20,000 hours,
AudioLM at 60,000 — are three orders of magnitude away, not one.

## What this changed

- **Do not collect audio for the generator.** The corpus growth running while this
  finished is not wasted — more corvid recordings help the classifier, the
  context work and every question about crows rather than about CrowGPT — but it
  will not make the generation better and should not be justified on that basis.
- **The Chinchilla argument is withdrawn**, along with the ranking of next steps
  built on it.
- **Stop proposing generator variants.** Six axes, six nulls. The next idea needs
  to explain why it differs in kind, not in degree, from the six that failed.
- **The honest pivot is the context work.** 0040 showed the question this project
  exists to answer — do call types form natural clusters — was measured in a
  space where the microphone outranks the species, so it has never really been
  asked. That is where the value is, and it needs more recordings, which is what
  is downloading.
- **A method note worth keeping:** this cost three runs and settled a question
  that five experiments had circled. A scaling curve is cheap and should come
  *before* architecture work, not after it.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0048-is-it-the-data/run.py
```

Three arms at ~60 min each; the 100% arm reuses `model-fair-k8`. Resumable per
arm. Writes `results.json` here.
