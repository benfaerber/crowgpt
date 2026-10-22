# 0024 — The xylophone, and the missing caws

Two questions from the same listening sittings, both raised by Ben unprompted
and neither previously measurable.

## Part 2 first, because it is the bigger result

**The generator makes one caw where the corpus makes four.**

From the second sitting: "I have noticed there are single `blips` where one caw
happens and I typically think those are AI but they turn out to be real." That
is a claim about the audio, so it is testable. `Segmenter` — 0013's burst
detector at its validated 12 dB, the same numerics that cut the corpus — was run
over the 60 clips already cached from that sitting.

| | real held-out | generated |
|---|---:|---:|
| clips | 30 | 30 |
| mean units | 3.37 | **1.37** |
| median units | 4.0 | **1.0** |
| single-unit share | 33% | **70%** |

```
real       0:2  1:8  2:4  4:3  5:8  6:3  7:1  8:1
generated  1:21 2:7  3:2
```

Mann-Whitney **p = 0.0008**. The real distribution runs from 0 to 8 units with a
mode at 5; the generated one never exceeds 3 and is 70% single caws.

**The sanity check passes**, which is what licenses reading any of this: real
bouts come out at mean 3.37 and median 4.0 against the ~3.8 units per bout 0013
measured on the corpus. The detector is being driven correctly.

**Ben's instinct was right and his examples were the exceptions.** Hearing a
single blip, P(generated) is 21/31 ≈ 68%, so guessing "AI" on a lone caw is
correct about two thirds of the time. The cases he remembered are the third where
it was not — availability, not a broken heuristic.

**Why this matters more than the tell.** Duration was never the discriminating
axis: 0021 measured generated bouts at 2.42–2.64 s against real ones at ~2.28 s,
and read the similarity as a null. It now looks like the wrong measurement rather
than a null result. Generated clips are the right LENGTH and the wrong DENSITY —
three seconds holding one caw and a lot of silence, where a real bout of the same
length holds four or five. That is a structural defect, it is almost certainly
audible, and nothing about it needs a listener to confirm.

It also reframes what the model failed to learn. `segment.py` says the bout unit
exists precisely so timing between calls is learnable — "a caw sequence has
timing, and a model trained on isolated 0.4 s units cannot learn it". The model
was given the unit that carries timing and did not learn to fill it.

### Caveat

Both arms sit in ambience from the same pipeline, so any burst the ambience
contributes is counted on both sides. That inflates both counts equally and
cannot manufacture a 3.37-versus-1.37 gap, but the absolute numbers are "units
in a clip", not "calls by a bird".

## Part 1 — is the xylophone the dead codebooks?

0019 measured stages 5, 6 and 7 predicting no better than the codec's own
marginal — three of eight codebooks carrying no learned signal. Ben has twice
described the defect as "choppy and changes tone rapidly" and "modem sounds",
with quality bimodal. Plausibly the same fact from two directions, never tested
by ear.

`results/compare-codebooks.html` decodes the same tokens three ways, so the only
thing that varies is what the fine stages contain:

- **full** — all eight codebooks as generated
- **coarse + marginal** — 0–4 kept, 5–7 redrawn from the per-codebook marginals
- **coarse only** — five codebooks, the rest dropped

Twelve generated bouts and twelve real held-out ones get identical treatment. The
real rows are the control that makes the page readable: five codebooks is a lower
bitrate whatever produced it, so a muffled `coarse only` needs a real row beside
it to say whether the model or the codec did that.

**Answered, 2026-08-01: no.** Ben's verdict on the page was that all three
variants of every row sound "almost identical" — so identical that he reported
one quality per row rather than per track.

That is two findings at once, and they point opposite ways.

**0019 is confirmed by ear.** Replacing codebooks 5-7 with noise drawn from the
codec's own marginals is inaudible. The model's fine stages really do carry no
more than a correctly-shaped histogram, exactly as the bits-per-stage table said.

**And the xylophone is NOT in them.** Dropping those stages entirely is also
inaudible, so the artefact survives their removal. Whatever produces "choppy,
changes tone rapidly" lives in codebooks **0-4** — the stages that do carry
learned signal — not in the three that do not. The hypothesis this experiment was
built to test is dead, which is the useful kind of dead: it was the leading
explanation and it is now excluded rather than lingering.

**The practical consequence is large and unrelated to quality.** Three of eight
codebooks can be dropped at no perceptual cost. A 3-second bout at 75 fps is
1,800 tokens at eight codebooks and 1,125 at five, and attention is quadratic —
roughly **61% less attention compute per bout**, or the same compute buying a
much longer context. Every training run in this project has been paying for
three stages that a listener cannot hear.

This also weakens a claim in the crowgpt README. "It is the model, not the codec"
rests on BirdNET detection holding 0.79-0.99 through the codec arm — but BirdNET
cannot hear "robotic", which is the stated reason the listening test exists at
all. The codec has never been judged on the artefact in question, and Ben's
notes on the REAL rows of this page ("choppy", "still bad") are the first
evidence that the round-trip itself may be audible. The page has no raw arm, so
that is not yet settled — see below.

## Part 3 — the codec itself, judged by ear at last

Part 1 left one page unread: `codec_only.py` pairs each held-out bout as RAW
against its own 6 kbps round-trip, no model anywhere, because "it is the
model, not the codec" had only ever been checked with BirdNET — which cannot
hear the artefact the claim is about.

**Answered, 2026-08-01: the round-trip is audible.** Ben's verdict on
`results/compare-codec-only.html`: *"through the codec it makes it scratchy
and worse."* Ten rows of raw-versus-codec, and the codec side is the scratchy
one.

That reopens the tokenizer as a lever. It does not rescue the model — the
interleaved sittings that tell generated from real at d′ = 1.34 were
comparisons where both sides carried codec scratch, so a model defect exists
on top. But it means every generated clip ships with a codec deficit already
in it, and no model-side change can remove that. The follow-up plan is
the timbre plan (since deleted; 0028 and 0039 carry what it concluded).

## What changed

- **A concrete, measurable defect exists and it is not timbre.** The generator
  under-produces call units by a factor of about 2.5. Every previous attempt to
  characterise "it sounds robotic" reached for spectral or codec-level
  explanations; this one is countable, and it was found by taking a listener's
  offhand remark literally.
- **Duration is confirmed as the wrong axis** and unit density as a right one.
  0021's duration null should be read as a mis-aimed measurement.
- **A candidate fix that is not more training.** If the model emits an EOS-shaped
  gap instead of the next caw, the levers are the duration token, the bout
  merging rule, or the loss on silence — none of which is capacity.
- **The tokenizer is back on the table.** The codec round-trip is audibly
  scratchy on its own (Part 3), so "the codec is not the lever" — the standing
  line since 0017 — is dead. What the smallest transparent codebook count is,
  nobody has measured; that is the first work package in PLAN-TIMBRE.

## Re-running

```bash
cd crowgpt
.venv/bin/python ../experiments/0024-is-the-xylophone-the-dead-codebooks/run.py    # page, ~5 GPU-min
.venv/bin/python ../experiments/0024-is-the-xylophone-the-dead-codebooks/units.py  # counts, no GPU
```
