# 0043 — Does pinning the channel fix the timbre?

**2026-08-03** · 67 held-out bouts, one per recording · 216 generations, no
listening sitting · **answer: the question was built on a number that does not
survive a change of checkpoint, and the arm that moved was the control**

## What this was for

0042 measured two defects in generated audio against a codec-carrying control:
timbre moving 17% faster frame to frame than real audio, and 23% less timbral
variety across clips. It read them as one mechanism — the corpus's dominant axis
of timbre is the microphone (6.2x more spread between recordings than within
one), the generator has no token for it, so it averages over ~12,800 channels.

Arm D tests that without training anything. A causal model conditions on
whatever is in its context, so seeding it with a real bout's opening second of
codec tokens pins the channel by example.

Arm C' tests the competing explanation, which two independent code audits found
on the same day. `top_k=200` is not a uniform truncation: on `model-fair-k8` it
retains 0.981 of the probability mass at stage 0 and 0.782 at stage 7. It is a
no-op on coarse structure and discards a fifth of the fine residual. That is
structurally the same operation as cooling the fine stages — which `stages.py`
pre-registered as the thing that would sound robotic, and which 0019 closed on
*calibration* grounds while checking top-k only against EOS, never against mass.

## Results

Same instrument as 0042, imported from it rather than reimplemented.
`model-fair-k8`, fresh held-out bouts, one per recording.

| arm | n | frame-to-frame | within-clip | between-clip |
|---|---|---|---|---|
| A real | 67 | 0.0413 | 0.0572 | 0.2003 |
| B real via codec | 67 | 0.0416 | 0.0575 | 0.1694 |
| C generated, top_k=200 | 56 | **0.0330** | **0.0438** | 0.1605 |
| C' generated, top_k=None | 54 | 0.0422 | 0.0620 | 0.1430 |
| D prompted continuation | 40 | **0.0572** | 0.0583 | 0.1918 |

| comparison | frame-to-frame | within-clip |
|---|---|---|
| C − B | **−0.0086** [−0.0151, −0.0020] | **−0.0137** [−0.0246, −0.0028] |
| C' − B | +0.0006 [−0.0067, +0.0079] | +0.0045 [−0.0085, +0.0177] |
| D − B | **+0.0155** [+0.0019, +0.0309] | +0.0007 [−0.0159, +0.0193] |
| C' − C | **+0.0092** [+0.0024, +0.0159] | **+0.0182** [+0.0060, +0.0300] |

Between-clip spread resolved nowhere: C − B is −0.009 [−0.053, +0.040], D − B is
+0.022 [−0.039, +0.080].

## The finding, and it is not the one this experiment was built to test

**0042's frame-to-frame defect does not reproduce on the incumbent, and its sign
is reversed.** 0042 measured generated audio moving *faster* than the codec arm
(+0.0098, resolved). Here the same statistic on the same instrument has it moving
*slower* (−0.0086, resolved). 0042's caveat was that its arms were the cached
2026-07-30 clips and had not been re-measured on `fair-k8`. They have been now,
and the number crossed zero.

So the incumbent's timbre is too **static**, not too jittery. That agrees with a
measurement made independently the same day by the sampling audit: generated
coarse stages repeat frame to frame 2–3.5x more often than real ones do, while
the fine residual comes out more random than real. A frozen carrier under a noisy
residual is a better description of "xylophone" than anything this project has
had, and it is the opposite of what 0042 inferred.

**Turning top-k off removes the defect on this instrument.** C' sits at 0.0422
against real audio's 0.0413 and the codec's 0.0416 on frame-to-frame, and 0.0620
against 0.0572 and 0.0575 on within-clip — both indistinguishable from real,
where the incumbent's settings are resolved below both. C' − C is resolved on
both statistics. The sampler, not the model, is flattening the output.

This costs nothing to change and has never been tested by ear at T=1.0. 0015
swept top-k on/off at five temperatures and found it hurt at every temperature
*except* 1.00 — and 1.00 is the shipped setting, so the one cell where the sweep
did not condemn it is the one the project runs in. Its evidence was BirdNET
detection, which 0014 established cannot hear quality.

**Arm D neither confirms nor refutes the channel hypothesis.** Pinning the
channel raises between-clip variety from 0.1605 to 0.1918, the only arm above
the codec control and nearest real audio's 0.2003 — the direction the hypothesis
predicts. The interval covers zero. It also overshoots frame-to-frame, landing
resolved *above* the codec arm. With the two statistics now pointing opposite
ways there is no clean reading, and D's n is 40 of 67, the weakest arm here.

## What this changed

- **0042's headline is downgraded to a fact about one checkpoint.** Its
  measurement stands; the generalisation does not. The instrument was right to
  ask for the incumbent and the answer was not the one expected.
- **`top_k=200` moves to the front of the queue**, ahead of channel
  conditioning. It is a one-line change, it is the largest measured deviation
  between what the model learned and what the sampler draws, and it is the only
  arm here that lands on top of real audio on both within-clip statistics.
  **The next thing owed is a sitting, not another offline arm** — this
  instrument cannot say whether a clip sounds like a crow, only whether its
  timbre moves like one.
- **The channel work is built but not earned.** `crowgpt.channel`, the
  vocabulary token and the batch-time splice are committed and tested, and the
  retrain is cheap because nothing has to be re-encoded. It should wait behind
  the top-k sitting rather than run on the strength of a directional
  non-resolution.
- **A caution about this instrument.** It reversed sign between two checkpoints
  of the same model on the same corpus. Read it as a description of an arm, not
  as a property of "the generator", and never across sittings — which is the
  same lesson 0038 recorded about the listening rig, now repeated for an
  automated one.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0043-does-pinning-the-channel-fix-the-timbre/run.py
```

About six minutes on the 4070 Ti. Writes `results.json` here and reports through
its `data/progress` record.
