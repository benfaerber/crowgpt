# 0024 — The xylophone, and the missing caws

## Overview

Two questions from the same listening sittings, both raised by the listener unprompted. First: does the "xylophone" artefact in generated crow calls live in the three codec codebooks that experiment 0019 showed carry no learned signal? Answer: no — dropping or randomising those codebooks is inaudible, so the artefact lives in the codebooks that do carry signal. Second: is the listener's hunch right that generated clips contain suspiciously few caws? Emphatically yes — the generator makes about one caw where the corpus makes four, a countable structural defect (Mann-Whitney p = 0.0008). A third finding fell out along the way: judged by ear for the first time, the codec's own round-trip is audibly "scratchy", reopening the tokenizer as a lever.

## In depth

### Part 2 — the missing caws (the bigger result)

From the second listening sitting: "I have noticed there are single `blips` where one caw happens and I typically think those are AI but they turn out to be real." That is a claim about the audio, so it is testable. `Segmenter` — experiment 0013's burst detector at its validated 12 dB, the same numerics that cut the corpus — was run over the 60 clips already cached from that sitting.

| | real held-out | generated |
|---|---:|---:|
| clips | 30 | 30 |
| mean units | 3.37 | 1.37 |
| median units | 4.0 | 1.0 |
| single-unit share | 33% | 70% |

Unit-count histograms:

```
real       0:2  1:8  2:4  4:3  5:8  6:3  7:1  8:1
generated  1:21 2:7  3:2
```

Mann-Whitney p = 0.0008. The real distribution runs from 0 to 8 units with a mode at 5; the generated one never exceeds 3 and is 70% single caws. The sanity check that licenses reading any of this passes: real bouts come out at mean 3.37 and median 4.0 against the roughly 3.8 units per bout that experiment 0013 measured on the corpus, so the detector is being driven correctly.

Ben's instinct was right and his remembered examples were the exceptions: hearing a single blip, P(generated) is 21/31 ≈ 68%, so guessing "AI" on a lone caw is correct about two thirds of the time. The cases he remembered are the third where it was not — availability, not a broken heuristic.

Why this matters more than the tell: duration was never the discriminating axis. Experiment 0021 measured generated bouts at 2.42–2.64 s against real ones at about 2.28 s and read the similarity as a null. That now looks like the wrong measurement rather than a null result — generated clips are the right *length* and the wrong *density*, three seconds holding one caw and a lot of silence where a real bout of the same length holds four or five. It also reframes what the model failed to learn: the bout unit exists precisely so timing between calls is learnable, and the model was given that unit and did not learn to fill it.

**Caveat:** both arms sit in ambience from the same pipeline, so any burst the ambience contributes is counted on both sides. That inflates both counts equally and cannot manufacture a 3.37-versus-1.37 gap, but the absolute numbers are "units in a clip", not "calls by a bird".

### Part 1 — is the xylophone the dead codebooks?

Experiment 0019 measured stages 5, 6 and 7 predicting no better than the codec's own marginal — three of eight codebooks carrying no learned signal. Ben had twice described the defect as "choppy and changes tone rapidly" and "modem sounds". Plausibly the same fact from two directions, never tested by ear.

A comparison page decoded the same tokens three ways, so the only thing varying is what the fine stages contain: **full** (all eight codebooks as generated), **coarse + marginal** (codebooks 0–4 kept, 5–7 redrawn from per-codebook marginals), and **coarse only** (five codebooks, the rest dropped). Twelve generated bouts and twelve real held-out ones got identical treatment; the real rows are the control that makes the page readable.

**Answered 2026-08-01: no.** Ben's verdict was that all three variants of every row sound "almost identical" — so identical that he reported one quality per row rather than per track. That is two findings pointing opposite ways:

- Experiment 0019 is confirmed by ear: replacing codebooks 5–7 with noise drawn from the codec's own marginals is inaudible. The fine stages really carry no more than a correctly-shaped histogram.
- And the xylophone is *not* in them: dropping those stages entirely is also inaudible, so the artefact survives their removal. Whatever produces "choppy, changes tone rapidly" lives in codebooks 0–4 — the stages that do carry learned signal. The leading explanation is now excluded rather than lingering.

The practical consequence is large and unrelated to quality: three of eight codebooks can be dropped at no perceptual cost. A 3-second bout at 75 fps is 1,800 tokens at eight codebooks and 1,125 at five, and attention is quadratic — roughly 61% less attention compute per bout, or the same compute buying a much longer context. Every training run in the project had been paying for three stages a listener cannot hear.

### Part 3 — the codec itself, judged by ear at last

The claim "it is the model, not the codec" had only ever been checked with BirdNET detection (holding 0.79–0.99 through the codec arm), and BirdNET cannot hear "robotic" — which is the stated reason the listening test exists at all. So each held-out bout was paired RAW against its own 6 kbps round-trip, no model anywhere.

**Answered 2026-08-01: the round-trip is audible.** Ben's verdict on the page: "through the codec it makes it scratchy and worse." Ten rows of raw-versus-codec, and the codec side is the scratchy one.

That reopens the tokenizer as a lever. It does not rescue the model — the interleaved sittings that tell generated from real at d′ = 1.34 compared clips that both carried codec scratch, so a model defect exists on top. But every generated clip ships with a codec deficit already in it, and no model-side change can remove that. The follow-up plan was the timbre plan (since deleted; experiments 0028 and 0039 carry what it concluded).

### What changed

- A concrete, measurable defect exists and it is not timbre: the generator under-produces call units by a factor of about 2.5. It was found by taking a listener's offhand remark literally, and nothing about it needs a listener to confirm.
- Duration is confirmed as the wrong axis and unit density as a right one; experiment 0021's duration null should be read as a mis-aimed measurement.
- A candidate fix that is not more training: if the model emits an EOS-shaped gap instead of the next caw, the levers are the duration token, the bout merging rule, or the loss on silence — none of which is capacity.
- The tokenizer is back on the table. The codec round-trip is audibly scratchy on its own, so "the codec is not the lever" — the standing line since experiment 0017 — is dead. The smallest transparent codebook count had never been measured; that became the first work package of the timbre plan.
