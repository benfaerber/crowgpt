# 0042 — Does the generator hold one voice?

**2026-08-03** · 70 real + 70 codec round-trips + 63 generated clips, all
cached · no listening sitting · **answer: no, and the two halves of "no" are
both resolved against a codec-carrying control**

## The question

Ben: *"Why does CrowGPT sound bad? What am I missing here?"*

The listener's description has been stable across thirty experiments, and the
distinctive half of it has never been turned into a number. Not "robotic" —
that is a summary. The specific words are **"xylophone-esque, choppy, changes
tone rapidly"**, and "changes tone rapidly" is a claim about a *rate*: how fast
timbre moves inside one clip.

0020 ran six hand-crafted timbre measures and found no separation between real,
codec and generated at n=40, and that null has been read ever since as "no cheap
instrument can hear this defect". Re-read the panel and the null is narrower than
that. HNR, jitter, spectral flatness, voiced fraction, the frame-grid stitch —
every one is a within-frame or whole-clip statistic. **Not one measures a rate of
change, and not one looks across clips.** The complaint is about both.

So: three questions, one instrument.

1. Within a clip, does generated timbre move faster frame to frame than real?
2. Across clips, does the generator produce as much timbral *variety* as real
   audio does — does it commit to a bird, or emit an average of all of them?
3. In the corpus, how much of real timbre variation is the *recording* rather
   than the bird? This is the scale the other two are read against.

## Method

MFCC 1–12 per frame, **c0 dropped and every vector unit-normalised**, so level
cannot be a cue — 0022 had to peak-normalise four arms before scoring, and this
avoids the problem rather than correcting it. Distances are cosine, so all four
statistics live on one scale and can be read against each other.

**Burst frames only**, at `segment.Segmenter`'s own 12 dB floor. Generated clips
carry fewer call units than real ones (0024: 1.37 against 3.37), so any statistic
over whole clips is partly a density statistic. Restricting to frames above the
burst floor removes that confound, which is the reason 0026's density result does
not have to be re-litigated here.

**Arm B is not optional.** 0024 established that the round-trip is itself audibly
scratchy, so a generated-vs-raw difference is uninterpretable — it could be the
tokenizer. Every claim below is **generated against B**, the same real clips
encoded and decoded through the shipped EnCodec. B against A is reported as the
check that the instrument is not merely reading the codec.

| | what it measures |
|---|---|
| frame-to-frame | mean distance between *consecutive* burst frames of a clip |
| within-clip | mean distance from a clip's burst frames to its own centroid |
| between-clip | spread of clip centroids around the arm's centroid |

Bootstrap 95% CIs throughout, resampling clips. Arms A and C are the cached
clips behind `results/clips.npz`, so the model here is the 2026-07-30 checkpoint
and no new generation was run.

## Results

| arm | n | frame-to-frame | within-clip | between-clip | within/between |
|---|---|---|---|---|---|
| A real | 70 | 0.0566 | 0.0808 | 0.2121 | 0.38 |
| B real via codec | 70 | 0.0580 | 0.0815 | 0.1881 | 0.43 |
| **C generated** | 63 | **0.0678** | 0.0791 | **0.1447** | **0.55** |

| comparison | difference | 95% CI | |
|---|---|---|---|
| B − A, frame-to-frame | +0.0014 | [−0.0091, +0.0114] | not resolved |
| B − A, within-clip | +0.0007 | [−0.0131, +0.0144] | not resolved |
| B − A, between-clip | −0.0240 | [−0.0681, +0.0206] | not resolved |
| **C − B, frame-to-frame** | **+0.0098** | [+0.0005, +0.0188] | **resolved** |
| C − B, within-clip | −0.0023 | [−0.0168, +0.0128] | not resolved |
| **C − B, between-clip** | **−0.0433** | [−0.0826, −0.0034] | **resolved** |

**The codec adds none of it.** All three B − A intervals cover zero. Whatever
this instrument is reading, the tokenizer is not putting it there — consistent
with 0020's `stitch_db` finding that the model adds nothing to the codec's frame
grid, and now extended to timbre rate and timbre variety.

**Two defects, and they are opposite in sign.**

- Generated audio traverses timbre **17% faster frame to frame** than the same
  audio through the same codec. This is the first number in the project that
  says "changes tone rapidly" rather than restating it.
- Generated audio has **23% less timbral variety across clips** than the codec
  arm, and 32% less than raw. Every generated clip sounds like a similar bird.

**Within-clip spread is identical everywhere** (0.081 in all three arms, no
interval close to resolving). So the generator is not drifting to a wrong timbre
and it is not covering a wider range. It covers the *same* range and moves
through it *faster*. The defect is a per-frame instability, not a drift — which
matters, because it rules out the "derailment" story (0018's untested U-shape
hypothesis: one implausible token puts the context off-distribution and nothing
recovers). Derailment predicts high within-clip spread. Within-clip spread is
flat.

### The scale those numbers are read against

Real American Crow bouts, grouped by the recording they were cut from:

| | cosine spread |
|---|---|
| within one recording | **0.0264** (median 0.0170) |
| between recordings | **0.1630** |
| ratio | **6.2×** |

**In this corpus the microphone moves timbre 6.2× further than everything inside
one microphone does — bird, call type, distance, day, all of it.** That is the
audio-domain twin of 0040, which found the same thing one day earlier in BirdNET
embedding space (recording identity +0.296 against species' +0.213) and drew the
consequence only for the clustering question.

## What this changed

**It names a mechanism that fits both defects at once, and it is not on the
closed list.** The corpus is 81,389 bouts over **12,846 recordings and 11,476
recordist-days** — 41.7 hours spread across roughly 12,800 acoustic channels, an
average of **11.7 seconds per channel**. The dominant axis of timbre variation in
the training data is the channel, by 6.2×, and `tokens.Vocabulary` conditions on
species, call type and duration — **there is no token for the channel.**

A model that cannot name the largest nuisance variable in its data has to average
over it. Averaging over ~12,800 channels produces exactly the pair of defects
measured here: a smeared mean voice that belongs to no particular microphone
(between-clip variety collapses) and a per-frame conditional too broad to hold
still, because nothing in the context pins the next frame to the channel the
last one came from (frame-to-frame rate rises). The listener hears an averaged
bird that rattles. That is what "xylophone" describes.

This also gives the mechanism for a rule the project already trusts on
evidence alone. **Validation loss does not predict what the listener hears**
(0023: 0.164 nats for a paired difference of 0.000; 0027: 0.15 nats for 1/12
against 1/12) — and the split is by group, so every val bout comes from a
recording whose channel the model has never heard. A large share of held-out
cross-entropy is channel entropy that is *irreducible by construction*. Moving
that number around says nothing about crows.

**It does not prove channel conditioning is the fix.** It establishes the two
symptoms and the scale of the nuisance variable. The causal claim needs the
conditioning arm, and the cheapest form of it needs no training at all — seed
the sampler with the first second of a real bout's codec tokens and free-run the
rest, which pins the channel by example. Re-run this measurement on the
continuations only. If frame-to-frame drops toward 0.058 and between-clip rises,
the mechanism is confirmed before a listening sitting is spent.

**A caveat and a correction, both worth carrying.**

- Arms A and C are the cached 2026-07-30 clips, not `fair-k8`. The defect is
  described identically across every checkpoint in the series, so it is expected
  to transfer, but this has not been re-measured on the incumbent.
- **`crowgpt/ASK-FOR-HELP.md` was stale in two load-bearing places.** (The brief
  has since been deleted; this is kept because the two numbers are the point.)
  It told an
  outside model the corpus is "2,672 archive recordings" (it is 12,846) and
  that "American Crow is only ~6% of the pool by unit count" (it is **70.6%** —
  0019 already recorded 70.6% and the brief carries 0013's figure from the
  original corpus). Both errors point advice away from the channel: they hide the
  number of channels and invent a data shortage on the target species that does
  not exist.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0042-does-the-generator-hold-one-voice/run.py
```

About a minute. Touches the GPU only for arm B's encode pass. Writes
`results.json` here.
