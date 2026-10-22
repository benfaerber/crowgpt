# Is it the data?

## Overview

After five modelling experiments in a row failed to improve the crow-call generator, the working theory became that the corpus was simply too small — a tokens-per-parameter argument borrowed from language-model scaling laws. This experiment tested that theory directly by training four otherwise-identical models on 12.5%, 25%, 50% and 100% of the corpus and watching how validation loss scaled. The answer is no: each doubling of the data bought about a third of what the previous one did, the gains had shrunk to a level an order of magnitude below one already measured to be inaudible, and the model at half the corpus was no longer overfitting at all. More data will not help the generator, and the original diagnosis was wrong.

## In depth

**The claim under test.** The argument was that 74M unique tokens (148M with augmentation) against the ~438M a 21.9M-parameter model wants by Chinchilla — 17% of it — made data the binding constraint. That reading explained everything at once, and it was checkable in three training runs, which is the only reason it is now known to be false.

**Method.** Same recipe throughout — d384/L8/H6, effective batch 18, dropout 0, 30,000 steps, EnCodec 8 codebooks — with the corpus subset **by recording group** and the validation split never subset, so the losses are comparable across arms.

**Result.**

| data | groups | tokens | best val | gain over previous | stage-0 churn |
|---|---|---|---|---|---|
| 12.5% | 1,205 | 18M | 4.9042 | — | 0.796 |
| 25% | 2,410 | 37M | 4.6814 | +0.2228 | 0.824 |
| 50% | 4,820 | 73M | 4.6047 | +0.0767 | 0.791 |
| 100% | 9,640 | 148M | 4.5874 | +0.0173 | 0.819 |

Each doubling buys about a third of what the previous one did. Extrapolating that ratio, every remaining recording in the world is worth roughly +0.026 nats, and the next doubling about +0.017. Put next to experiment 0023 — where a 0.164-nat improvement produced a listening difference of exactly zero — doubling the corpus buys a change an order of magnitude smaller than one already measured to be inaudible. Stage-0 churn agrees and is flat: 0.796, 0.824, 0.791, 0.819 against real audio's 0.868, with no trend across an eightfold change in data, so the "crow plus modem" defect does not improve with more corpus either.

**The train/val gaps show where the transition happens.**

| data | final gap | stopped at |
|---|---|---|
| 12.5% | +0.5977 | 18,000 (early) |
| 25% | +0.1302 | 30,000 |
| 50% | +0.0160 | 30,000 |
| 100% | +0.0482 | 30,000 |

At an eighth of the corpus the model memorises hard and early-stops. By half, the gap is 0.016 — it is not overfitting and not memorising; it simply cannot do better. That is the signature of a model at the limit of what the objective extracts, not one starved of examples.

**What was wrong, and why.** Chinchilla is a compute-optimal allocation result for language models — given a fixed budget, how to split it between parameters and tokens. It is not a claim that a model below that ratio is starved in a way more data repairs; a ratio was read as a diagnosis and it is not one. The evidence against it was already on disk: experiments 0023 and 0038 both found capacity not converting to audible quality, and a genuinely data-starved model is one where capacity does convert once data is added. Three training runs was the right price to find out; the wrong price was the two days of modelling variants that came first.

**Where this leaves the generator.** Every axis has now been measured and none of them moves generated audio:

| lever | verdict |
|---|---|
| tokenizer | four configurations, no movement (experiments 0028, 0032–0037) |
| capacity | ruled out twice, two sizes, two sequence lengths (0023, 0038) |
| sequence length | shortening hurt badly (0038) |
| architecture | extender dead (0035), delay pattern null (0045) |
| sampling | churn reachable, audibility unresolved (0044, 0046, 0047) |
| **data** | **flat past 50% (this experiment)** |

The model's validation loss floor is ~4.59 nats — 6.62 bits per token against the codec's 8.98-bit marginal, so it recovers 2.36 bits, and neither more data nor more parameters move that. The most economical reading is that it sits at the conditional entropy of this token stream: given this tokenizer and this objective, the next token genuinely is that uncertain. That is not a claim the audio cannot be improved — it is a claim that next-token cross-entropy over RVQ acoustic tokens has given what it has to give at this scale, and the systems that make this approach work (MusicGen at 20,000 hours, AudioLM at 60,000) are three orders of magnitude away, not one.

**What this changed:**

- **Do not collect audio for the generator.** The corpus growth already running is not wasted — more corvid recordings help the classifier, the context work and every question about crows rather than about CrowGPT — but it will not make generation better and should not be justified on that basis.
- The Chinchilla argument is withdrawn, along with the ranking of next steps built on it.
- **Stop proposing generator variants.** Six axes, six nulls; the next idea needs to explain why it differs in kind, not in degree, from the six that failed.
- The honest pivot is the context work: experiment 0040 showed that the question this project exists to answer — do call types form natural clusters — was measured in a space where the microphone outranks the species, so it has never really been asked.
- A method note worth keeping: this cost three runs and settled a question five experiments had circled. A scaling curve is cheap and should come before architecture work, not after it.
