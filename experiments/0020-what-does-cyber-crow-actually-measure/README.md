# What does "cyber crow" actually measure?

2026-07-31 · `model-d384-6k` · 40 bouts per arm, American Crow, raw audio with no
ambience · `run.py`

## Why

Ben's verdict on the best model is *"more like a cyborg, so still a little
robotic but still a crow"*, and nothing in the project can measure that. BirdNET
detection is at 96% of its codec ceiling, and 0014 disqualified it for quality
outright — a 2 kHz lowpass, audibly destroyed, retained *more* detections
(0.733) than a 3 kbps codec round-trip (0.690) while sitting 3.2× further away
spectrally. Fréchet distance still discriminates but is one opaque scalar that
cannot say *what* is wrong.

So: three cheap interpretable measures, with the acceptance test written down
first. A measure earns its place only if **real ≈ codec while generated differs
from both**. Separating real from codec means it is describing the tokenizer,
which 0014 and 0017 already cleared. Separating nothing means delete it.

## What it found

**A null. None of the three measures separates generated audio from
codec-round-tripped audio at n = 40.**

| measure | A real | B codec | C generated |
|---|---|---|---|
| stitch_db | **0.264** [−1.40, 1.63] | 12.567 [9.94, 13.15] | 12.902 [11.05, 14.31] |
| hnr_db | 2.555 [0.57, 3.33] | 2.590 [0.63, 3.84] | 1.827 [1.31, 2.54] |
| crest | 3.324 [2.77, 3.70] | 2.989 [2.60, 3.46] | 2.915 [2.61, 3.12] |
| voiced_fraction | 0.965 [0.84, 0.99] | 0.961 [0.81, 0.99] | 0.985 [0.98, 0.99] |
| rise_ms | 4.000 [2.00, 4.00] | 4.000 [4.00, 4.00] | 4.000 [4.00, 6.00] |
| jitter | 0.001 [0.00, 0.01] | 0.003 [0.00, 0.01] | 0.011 [0.00, 0.02] |

Medians with bootstrap intervals. Every generated value sits inside the codec
arm's interval.

`hnr_db` is directionally lower for generated (1.83 against 2.59) and
`voiced_fraction` slightly higher, but both intervals overlap comfortably. At
this n they are hints, not findings, and quoting them as anything else would be
the thing this project keeps having to correct.

### The one thing that worked perfectly is the null itself

`stitch_db` was built with a null known by construction rather than measured:
real audio has no reason to prefer any particular codec frame phase, so it
should score zero without anyone calibrating it. **It scores 0.264 dB.** In the
earlier, confounded run of this experiment it scored 0.528 dB on entirely
different audio. The measure is sound.

What it measures is also real and large — anything through EnCodec picks up a
**~12.5 dB signature at exactly 75 Hz**, the codec's own frame rate. That is a
substantial, previously unmeasured artefact of the tokenizer.

It is just not what separates the model from the codec. Codec and generated are
12.57 and 12.90, indistinguishable. **The frame grid is entirely the codec's,
and the model adds nothing detectable on top of it.** Since Ben's own comparison
already found the codec arm "holds up" by ear, the 75 Hz grid is demonstrably
not what makes the output sound robotic, and nobody should go chasing it.

### A methodological trap, recorded because it nearly worked

The first version of this experiment scored the clips the listening test plays —
a bout dropped into three seconds of real ambience — and produced a clean-looking
result: codec 13.4 dB against generated 7.0 dB, i.e. "the tokenizer is worse than
the model". That was an artefact of unequal treatment. A generated clip is codec
output only where the bout is and untouched ambience everywhere else, while a
round-tripped clip is codec output for the full three seconds. The codec arm
simply contained more codec.

With raw bouts and equal treatment the two arms land on top of each other. The
lesson is cheap to state and was nearly expensive: **an arm is not a control
unless every stage that touches the audio touches it the same number of times.**

`jitter` also had to be fixed mid-experiment. Integer-lag autocorrelation gives
about a 3% f0 grid at 24 kHz, so every frame-to-frame change smaller than that
read as exactly zero, and the first run returned 0.000 for real and generated
alike — a quantisation artefact wearing the costume of a null. Parabolic
interpolation on the autocorrelation peak fixed it. It still does not separate
anything, but it now fails honestly.

## What this changed

- **The timbre panel does not gate anything.** It was going to be the cheap
  pre-filter deciding whether a change deserved an hour of Ben's listening.
  It cannot do that job, and nothing should be promoted or rejected on it.
- **Ruled out the codec frame grid as the source of roboticness**, with a number:
  the model contributes no measurable frame-stitch beyond what the codec already
  puts there. This closes a plausible-sounding line of attack.
- **`stitch_db` is kept** — not as a quality measure but as a working detector of
  codec-grid artefacts, with a verified structural zero. If a future change
  (different codec, different bitrate, splicing) is suspected of adding
  discontinuities, this is the instrument, and it needs no baseline run.
- **`hnr_db`, `crest`, `voiced_fraction`, `rise_ms`, `jitter` are not deleted but
  are demoted to descriptive.** Re-run at n in the low hundreds before believing
  the HNR hint; at n = 40 the intervals cannot resolve a difference this size.
- **The instrument problem is not solved.** The recorded listening test remains
  the only thing that can currently judge "less robotic", which raises the value
  of the sessions being kept rather than thrown away.

## Re-running

```bash
cd ../../crowgpt && PYTHONPATH=src .venv/bin/python \
    ../experiments/0020-what-does-cyber-crow-actually-measure/run.py -n 40
```

Generation dominates the runtime — about ten minutes for 40 bouts on a shared
GPU. Raise `-n` to chase the HNR hint.
