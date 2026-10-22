# Does the generator hold one voice?

## Overview

The listener has described generated crow audio as "xylophone-esque, choppy, changes tone rapidly" across thirty experiments, and this experiment turned that description into numbers for the first time by measuring how fast timbre moves within a clip and how much timbral variety exists across clips. Against a control of the same real audio passed through the codec, generated audio (the cached 2026-07-30 checkpoint) moved through timbre 17% faster frame to frame and showed 23% less variety across clips — both resolved, and both absent from the codec arm, so the tokenizer is not the source. The experiment also measured that in the training corpus the recording channel (microphone, gain, background) moves timbre 6.2 times further than everything within one recording combined, and proposed channel averaging as a mechanism fitting both defects. A caveat recorded here proved important: the arms were one checkpoint, and experiment 0043 later found the frame-to-frame result does not transfer to the incumbent model.

## In depth

### The question

Three questions, one instrument, run on 70 real clips, 70 codec round-trips, and 63 generated clips, all cached — no listening sitting and no new generation. First, does generated timbre move faster frame to frame than real? Second, does the generator produce as much timbral variety across clips as real audio — does it commit to a bird, or emit an average of all of them? Third, how much of real timbre variation is the recording rather than the bird — the scale the other two are read against?

0020's six hand-crafted timbre measures had found no separation at n=40, but every one was a within-frame or whole-clip statistic: not one measured a rate of change, and not one looked across clips, which is what the complaint is about.

### Method

MFCC 1–12 per frame, c0 dropped and every vector unit-normalised so level cannot be a cue. Distances are cosine, so all four statistics live on one scale. Burst frames only, at `segment.Segmenter`'s 12 dB floor — generated clips carry fewer call units than real ones (0024: 1.37 against 3.37), so any whole-clip statistic is partly a density statistic, and the burst restriction removes that confound. Arm B (the same real clips encoded and decoded through the shipped EnCodec) is not optional: 0024 established the round-trip is itself audibly scratchy, so every claim is generated against B, with B against A as the check that the instrument is not merely reading the codec. Bootstrap 95% CIs throughout, resampling clips.

### Results

| arm | n | frame-to-frame | within-clip | between-clip | within/between |
|---|---|---|---|---|---|
| A real | 70 | 0.0566 | 0.0808 | 0.2121 | 0.38 |
| B real via codec | 70 | 0.0580 | 0.0815 | 0.1881 | 0.43 |
| C generated | 63 | 0.0678 | 0.0791 | 0.1447 | 0.55 |

| comparison | difference | 95% CI | |
|---|---|---|---|
| B − A, frame-to-frame | +0.0014 | [−0.0091, +0.0114] | not resolved |
| B − A, within-clip | +0.0007 | [−0.0131, +0.0144] | not resolved |
| B − A, between-clip | −0.0240 | [−0.0681, +0.0206] | not resolved |
| C − B, frame-to-frame | +0.0098 | [+0.0005, +0.0188] | resolved |
| C − B, within-clip | −0.0023 | [−0.0168, +0.0128] | not resolved |
| C − B, between-clip | −0.0433 | [−0.0826, −0.0034] | resolved |

The codec adds none of it: all three B − A intervals cover zero. Two defects, opposite in sign: generated audio traverses timbre 17% faster frame to frame than the same audio through the same codec — the first number in the project that says "changes tone rapidly" rather than restating it — and has 23% less timbral variety across clips than the codec arm (32% less than raw). Within-clip spread is identical everywhere (0.081 in all three arms), so the generator is not drifting to a wrong timbre: it covers the same range and moves through it faster. That rules out the "derailment" story (0018's untested U-shape hypothesis), which predicts high within-clip spread.

The scale: real American Crow bouts grouped by source recording show cosine spread of 0.0264 within one recording (median 0.0170) against 0.1630 between recordings — a ratio of 6.2×. The microphone moves timbre 6.2 times further than everything inside one microphone does — bird, call type, distance, day, all of it. This is the audio-domain twin of 0040's finding in BirdNET embedding space (recording identity +0.296 against species' +0.213).

### The proposed mechanism

The corpus is 81,389 bouts over 12,846 recordings and 11,476 recordist-days — 41.7 hours spread across roughly 12,800 acoustic channels, an average of 11.7 seconds per channel — and `tokens.Vocabulary` conditions on species, call type and duration but carries no token for the channel. A model that cannot name the largest nuisance variable in its data has to average over it, which produces exactly this pair of defects: a smeared mean voice belonging to no particular microphone (between-clip variety collapses) and a per-frame conditional too broad to hold still (frame-to-frame rate rises). This also explains why validation loss does not predict what the listener hears (0023, 0027): the split is by group, so a large share of held-out cross-entropy is channel entropy that is irreducible by construction.

It does not prove channel conditioning is the fix — the causal claim needs a conditioning arm. The cheapest form proposed: seed the sampler with the first second of a real bout's codec tokens, free-run the rest, and re-run this measurement on the continuations (this became experiment 0043's arm D).

### Caveats

- Arms A and C are the cached 2026-07-30 clips, not `fair-k8`; the defect had not been re-measured on the incumbent at the time of writing. (Experiment 0043 then did, and the frame-to-frame sign reversed — this README's headline is a fact about one checkpoint.)
- These are corpus-level pipeline measurements over archive audio, not findings about the field recordings or particular crows.
- A correction found on the way: `crowgpt/ASK-FOR-HELP.md` (since deleted) was stale in two load-bearing places — it said the corpus is "2,672 archive recordings" (it is 12,846) and that "American Crow is only ~6% of the pool by unit count" (it is 70.6%). Both errors pointed advice away from the channel.

### What this changed

It named a mechanism — channel averaging — fitting both measured defects at once, and it established the two symptoms and the 6.2× scale of the nuisance variable, which set up the conditioning test in 0043 and the channel-token arm in 0044. Read together with those later experiments, the durable part is the between-clip variety collapse and the channel-scale measurement; the frame-to-frame number did not survive a change of checkpoint.
