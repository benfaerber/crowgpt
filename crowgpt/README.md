# crowgpt

Generating crow calls from the archive corpus. A small transformer trained from
scratch on call bouts, with **no human labelling anywhere in the loop**.

> **The results below stop at 2026-07-31.** Everything measured since — call-type
> conditioning working, three of eight codebooks carrying no learned signal, the
> model being underfit, and three retractions — is in
> [`experiments/`](../experiments/), one folder per question. A summary lived
> here and was deleted on 2026-08-05 for drifting out of agreement with the
> folders; they are the source of truth and always were.

Experiment 0013 established that the corpus could pay for this and that only
*call-type* conditioning ("say an alarm call") was out of reach — 67.7 seconds
of human ground truth, 5 labels isolating a single call. `FUTURE.txt` filed
CrowGPT with a second trigger: *"or when an unconditioned 'does it sound like a
crow at all' demo is wanted for its own sake — that one needs nothing that is
not already on disk."* This is that demo.

## Run

Every stage runs in this module's own venv, which carries torch and birdnetlib
together so extraction and training never hand off through a second interpreter.

```bash
make venv       # one-off, several GB — torch cu128 + birdnetlib + tflite
make test
make extract    # corpus -> call bouts    (~35 min, reports via make watch)
make gate       # can a codec carry a caw? -> experiments/0014
make tokenize   # bouts -> token memmaps  (BW=6.0 to override bandwidth)
make train      # ~10 min on a 4070 Ti SUPER
make judge      # four-arm BirdNET judgement + memorisation
make demo       # results/demo.html
```

## Releases

Two models have actually shipped — they are the ones on the promo site — and
everything else under `results/model-*` is an experiment. A release is a full
recipe, not a checkpoint; each lives in `results/releases/<name>.json` with its
provenance, loaded by `crowgpt.releases`:

```python
from crowgpt import releases

r = releases.load("crowgpt2")
sampler = r.sampler()          # checkpoint + the release's decoder, wired
r.sampling                     # {"temperature": 1.1, "top_k": 200, "max_frames": 460}
```

- **CrowGPT1** — `model-mono-v2` through the frozen decoder at T 1.0 / k 200,
  3 s window. The 0055 shortlist; seed 197 is the promo page's first clip.
- **CrowGPT2** — `model-longctx` through the 0063 adversarial decoder finetune
  at T 1.1 / k 200, 6 s window. The 0073 shortlist. The decoder is part of the
  name: this checkpoint decoded frozen is not CrowGPT2.

`make gate` is a stop point, not a step. If it fails at every bitrate the token
route is dead and the answer is a different codec, not more training.

## What it does

**Extract** re-runs experiment 0013's burst detector and *keeps the audio* —
0013 measured the units and threw the boundaries away ("returns summary counts
and the per-unit durations, never audio"), so nothing on disk had them.
Thresholds and the crow-name list are imported from `analyzer/birdnet.py` rather
than restated, so the gate is the one the pipeline actually uses.

The threshold is **12 dB**, not the 8 dB that 0013's `run.py` defaults to; its
section E showed 6 dB goes flat against the confidence gradient and is mostly
background.

**The unit is a bout, not a call.** Bursts within 1.5 s merge, capped at 3.0 s —
BirdNET's own window, so a generated bout is directly judgeable. The obvious
alternative, training on 0.4 s calls and assembling them for evaluation, would
inject a hand-invented prior about inter-call timing at exactly the point where
realism is being measured. This way timing is learned.

**Tokenize** encodes bouts with EnCodec at 24 kHz and flattens the residual
codebooks into one stream, each codebook keeping its own slice of the vocabulary
because residual stages are unrelated to one another. Augmentation is free: the
codec's hop is 320 samples, so cropping at a 40-sample offset yields a genuinely
different token sequence for audio no ear can tell apart.

**Train** fits a ~6M-parameter causal transformer. Small deliberately — the
corpus is millions of tokens but only a couple of thousand independent
recordings, and a 25M-parameter model on that memorises. Species conditioning is
a prefix token, and is free and trustworthy because BirdNET's species ID is what
selected the windows in the first place.

**Judge** scores four arms with BirdNET, the same detector that chose the
training data.

## The two things that are easy to get wrong

**BirdNET silently ignores short audio.** `birdnetlib` breaks out of its chunking
loop on anything under 1.5 s and returns zero detections with no error, so a
0.4 s clip judged alone reads as rejection when nothing was analysed at all.
Every arm is rendered as exactly 3.0 s in real ambience, never zero-padded —
digital silence is itself out of distribution and depresses confidence.

**Real versus generated is not the comparison.** It conflates a codec that threw
the caw away with a model that never learned it. The four arms are real (A),
real round-tripped through the codec (B), generated (C), and tokens drawn from
each codebook's marginal (D). **The claim "the model learned the distribution"
is B versus C.**

## Results, 2026-07-30

25,227 bouts / 12.75 hours from 2,672 recordings, zero read errors. A quarter of
raw bouts (8,484) were dropped for not landing in a corvid window, and the
recordist-announcement tail trim cost only 1,347 more — now measured rather than
assumed. Tokenised at 6 kbps into 171,510 training sequences via 8× sub-hop
augmentation. 7.3M parameters, trained in 6.5 minutes on a 4070 Ti SUPER, best
validation loss 5.155 against a training loss of ~4.89 — no meaningful gap.

### Does BirdNET think it is a crow?

| arm | detected as corvid | mean conf | species named right |
|---|---|---|---|
| A · real held-out | 88.9% | 0.730 | 72.2% |
| **B · real through the codec** | **80.6%** | 0.623 | 69.4% |
| **C · generated** | **38.9%** | 0.248 | 48.6% |
| D · unigram control | 0.0% | 0.000 | 0.0% |

**B versus C is the comparison**, and it says the model reaches a little under
half of its tokenizer's ceiling. The control is what makes that meaningful:
tokens drawn from the right marginal distribution and decoded the same way score
**zero**, so 38.9% is structure the model learned rather than an artefact of the
ambience, the decoder or the 3-second framing.

Arm B independently reproduces experiment 0014's measured codec ceiling (80.6%
here, 81.0% there) on entirely different audio, which is a reassuring sign that
neither number is a fluke.

### Did it just copy?

Exact overlap against canonical training n-grams, generated versus **held-out
real audio scored identically** — real crows share n-grams with other real crows,
so the base rate is the whole point.

| span | generated | held-out real | ratio |
|---|---|---|---|
| ~107 ms (8 frames) | 98.6% | 52.1% | 1.9× |
| ~213 ms (16 frames) | **37.5%** | **4.3%** | **8.7×** |
| ~427 ms (32 frames) | **11.4%** | **0.06%** | **190×** |

**Retracted — this was mode-seeking, not memorisation.**
[Experiment 0015](../experiments/0015-is-it-copying-or-playing-it-safe/) swept
the sampling temperature and the overlap melts with it: 22× the base rate at
T=0.70, and **1.0× — exactly the held-out real rate — at T=1.15**, with no loss
of detection. Memorised content does not evaporate when you raise the
temperature. The 37.5% was a property of the shipped sampling defaults
(T=0.95, top-k 200), which had never been measured, and not of the model.

The default is now **T=1.15 / top-k 200**, where generated audio matches the
training set no more often than recordings the model has never heard.

The table above is kept because it is how the question got asked, and because
the measurement is only interpretable next to the held-out base rate. Neither
number means anything alone.

The measurement only works at the coarse resolution. Matching across all eight
codebooks means 64 identical tokens in a row, which returns 0.0% for generated
*and* for held-out real audio — a test with no power, which is what the first
version of this check was.

### The listening log

BirdNET cannot hear "robotic", so the only instrument for it is a person. These
are Ben's verdicts in order, against the measured detection rate at the time —
worth keeping because the ear caught two things the numbers got wrong, and
because "sounds like a crow" is the actual goal.

| model | detected | verdict |
|---|---|---|
| 6k steps, 12.75 h | 38.9% | *"vaguely crow like"* |
| 24k steps, 12.75 h | 61.1% | *"still scratchy but now it sounds like a robo crow"* |
| 40k steps, 41.7 h, 18M | 66.7% | *"american crow is getting really good... more like a cyborg, so still a little robotic but still a crow"* |

The ear also (1) identified American Crow and Raven as the strong species when
the raw per-species scores said Raven was the worst — it was right, and the
scores were unnormalised (0016); and (2) reported the output as bimodal, "either
pretty good or pretty bad", which the confidence histogram then confirmed at 28%
near-zero and 25% strong.

**The first blinded sitting, 2026-07-31.** Every row above is an impression
offered while knowing which clip was which. Sixty forced-choice trials on
`model-d384-6k` (fingerprint `212a07123d27`), thirty real held-out bouts against
thirty generated, answers recorded per trial:

| n | correct | 95% CI | d′ | verdict |
|---|---|---|---|---|
| 60 | 75.0% | [63%, 85%] | 1.34 | can tell |

Chance is the target, so this is a loss rather than a score: the interval sits
clear of 50%, and the model has not arrived. But the shape is more encouraging
than the headline. **Ten of thirty generated clips passed as real**, and five of
thirty real bouts were called generated — the errors run in both directions,
which a merely robotic output would not produce. Decisions took a median of 2.2
seconds on a single play, so this is a first-impression judgement, not a hunt
for artifacts.

> *"Some are scratchy still or have a single blip or audio. Most are pretty
> good. Some also sound kind of xelophone-esque where its like choppy and
> changes tone rapidly"*

That last clause is the ear landing on 0019's measurement from the other side.
Stages 5, 6 and 7 of the codec predict no better than drawing from the marginal,
so three of eight codebooks are effectively noise laid over a decent coarse
signal — and "choppy, changes tone rapidly" is what that sounds like. A
bits-per-stage table and a listener reaching the same place independently is the
strongest evidence the project has for where the remaining roughness lives.

Run `make listen` for the pooled report; sittings pool by weight hash, never by
folder name.

### It is the model, not the codec

`make compare` puts the same window side by side as a real recording, as that
recording round-tripped through the codec touching no model, and as a
generation. Across six species the codec arm holds up — it scores 0.79 to 0.99
and on American Crow it actually beats the original — while the generated arm
sits at 0.0 to 0.69.

So the roughness people hear is the **model**, not the tokenizer. Raising the
bitrate to 12 kbps would buy 0.877 codec retention against 0.810 and change
nothing audible, while doubling the sequence length. The levers that matter are
training length, capacity and sampling temperature.

## What this inherits and cannot fix

The burst detector is a bootstrap, not a call detector. 0013 measured 1.02 units
per window even in its emptiest confidence band, so a minority of training audio
is not crow, and the model inherits that. The BirdNET corvid filter removes the
worst of it — a measured 24.5% of bouts — but not all.

Species conditioning works. **Call-type conditioning does not and is not
attempted here**, for the reason 0013 gives: the audio and the ability to label
it are anti-correlated across species. The only head good enough to pseudo-label
with is American Crow, and it sits on 6% of the pool.

## Grouping, and the asymmetry that is now fixable

Groups keep the same bird out of both sides of a split, because recordists
upload one bird on one day under several ids. American Crow was always grouped
properly — `corvid.db` keeps its full source record, and recordist + date +
locality collapse its 173 recordings into 144 independent groups.

The five species fetched earlier have manifests carrying only
`{id, type, path, quality}` and still fall back to per-recording grouping, which
is weaker. That is no longer a property of the corpus, only of when it was
fetched: the corpus tooling writes recordist, date and locality on every record
now, so **re-fetching a species upgrades its grouping**.
`corpus.py` uses the richer key whenever the manifest has it.

## Files

| | |
|---|---|
| `segment.py` | 0013's burst detector at 12 dB, extended to bouts |
| `corpus.py` | both corpus sources, including American Crow's separate path |
| `extract.py` | corpus -> bout shards + index |
| `codec.py` | EnCodec wrapper; flatten/unflatten |
| `metrics.py` | multi-resolution STFT distance, codebook entropy |
| `gate.py` | the feasibility measurement (experiment 0014) |
| `tokens.py` | tokenising, augmentation, the grouped three-way split |
| `model.py` | the transformer and its legality mask |
| `train.py` `sample.py` | training and generation |
| `judge.py` | four-arm BirdNET judgement, n-gram memorisation |
| `demo.py` | the self-contained listening test |

Bout shards and token memmaps live under `data/crowgpt/`, which is gitignored —
do not publish the shards.
