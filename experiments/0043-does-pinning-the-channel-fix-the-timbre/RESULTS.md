# Does pinning the channel fix the timbre?

## Overview

Experiment 0042 had measured generated audio moving through timbre 17% faster than real audio and blamed the model's inability to name the recording channel; this experiment tested that hypothesis by seeding the generator with the opening second of a real bout's tokens, alongside a competing explanation that the `top_k=200` sampling setting was truncating the fine codebook stages. Re-run on the current incumbent model, 0042's headline defect did not reproduce — the sign reversed, with the incumbent's timbre now too static rather than too jittery — and turning top-k off put the timbre statistics on top of real audio. The channel-pinning arm moved in the predicted direction on variety but did not resolve. The practical outcome was that the top-k question jumped to the front of the queue (settled by ear in experiment 0044), and the timbre instrument earned a standing caution: it describes one arm at one checkpoint and must not be generalised.

## In depth

### What this was for

0042 measured two defects against a codec-carrying control — timbre moving 17% faster frame to frame, and 23% less variety across clips — and read them as one mechanism: the corpus's dominant axis of timbre is the microphone (6.2× more spread between recordings than within one), the generator has no token for it, so it averages over roughly 12,800 channels.

Arm D tests that without training anything: a causal model conditions on whatever is in its context, so seeding it with a real bout's opening second of codec tokens pins the channel by example. Arm C' tests the competing explanation, found the same day by two independent code audits: `top_k=200` is not a uniform truncation — on `model-fair-k8` it retains 0.981 of the probability mass at stage 0 and 0.782 at stage 7, a no-op on coarse structure that discards a fifth of the fine residual. That is structurally the same operation as cooling the fine stages, which `stages.py` pre-registered as the thing that would sound robotic, and which 0019 closed on calibration grounds while checking top-k only against EOS, never against mass.

### Method

Same instrument as 0042, imported from it rather than reimplemented. `model-fair-k8`, 67 fresh held-out bouts, one per recording; 216 generations; no listening sitting.

### Results

| arm | n | frame-to-frame | within-clip | between-clip |
|---|---|---|---|---|
| A real | 67 | 0.0413 | 0.0572 | 0.2003 |
| B real via codec | 67 | 0.0416 | 0.0575 | 0.1694 |
| C generated, top_k=200 | 56 | 0.0330 | 0.0438 | 0.1605 |
| C' generated, top_k=None | 54 | 0.0422 | 0.0620 | 0.1430 |
| D prompted continuation | 40 | 0.0572 | 0.0583 | 0.1918 |

| comparison | frame-to-frame | within-clip |
|---|---|---|
| C − B | −0.0086 [−0.0151, −0.0020] | −0.0137 [−0.0246, −0.0028] |
| C' − B | +0.0006 [−0.0067, +0.0079] | +0.0045 [−0.0085, +0.0177] |
| D − B | +0.0155 [+0.0019, +0.0309] | +0.0007 [−0.0159, +0.0193] |
| C' − C | +0.0092 [+0.0024, +0.0159] | +0.0182 [+0.0060, +0.0300] |

Between-clip spread resolved nowhere: C − B is −0.009 [−0.053, +0.040], D − B is +0.022 [−0.039, +0.080].

### The finding, and it is not the one this experiment was built to test

0042's frame-to-frame defect does not reproduce on the incumbent, and its sign is reversed: 0042 measured generated audio moving faster than the codec arm (+0.0098, resolved); here the same statistic on the same instrument has it moving slower (−0.0086, resolved). 0042's caveat — that its arms were the cached 2026-07-30 clips, untested on `fair-k8` — was exactly the load-bearing one. So the incumbent's timbre is too static, not too jittery, agreeing with an independent sampling audit made the same day: generated coarse stages repeat frame to frame 2–3.5× more often than real ones while the fine residual comes out more random than real. A frozen carrier under a noisy residual is a better description of "xylophone" than anything the project had, and it is the opposite of what 0042 inferred.

Turning top-k off removes the defect on this instrument: C' sits at 0.0422 against real audio's 0.0413 and the codec's 0.0416 on frame-to-frame, and 0.0620 against 0.0572/0.0575 on within-clip — indistinguishable from real on both, where the incumbent's settings are resolved below both. C' − C is resolved on both statistics. The sampler, not the model, is flattening the output. The change costs nothing and had never been tested by ear at T=1.0: 0015 swept top-k at five temperatures and found it hurt at every temperature except 1.00 — the shipped setting — and its evidence was BirdNET detection, which 0014 established cannot hear quality.

Arm D neither confirms nor refutes the channel hypothesis. Pinning the channel raises between-clip variety from 0.1605 to 0.1918, the only arm above the codec control and nearest real audio's 0.2003 — the predicted direction — but the interval covers zero. It also overshoots frame-to-frame, landing resolved above the codec arm, and its n of 40 of 67 makes it the weakest arm here.

### Caveats

- No listening sitting was run: this instrument cannot say whether a clip sounds like a crow, only whether its timbre moves like one. (Experiment 0044 then ran the sitting, and the ear preferred `top_k=200` — the opposite of this instrument's ranking.)
- The instrument reversed sign between two checkpoints of the same model on the same corpus. Read it as a description of an arm, never across sittings — the same lesson 0038 recorded for the listening rig, repeated for an automated one.

### What this changed

- 0042's headline is downgraded to a fact about one checkpoint; its measurement stands, the generalisation does not.
- `top_k=200` moved to the front of the queue, ahead of channel conditioning — a one-line change and the largest measured deviation between what the model learned and what the sampler draws. The next thing owed was a sitting, not another offline arm.
- The channel work was built but not earned: `crowgpt.channel`, the vocabulary token and the batch-time splice are committed and tested, but the retrain waits behind the top-k sitting rather than running on a directional non-resolution.
