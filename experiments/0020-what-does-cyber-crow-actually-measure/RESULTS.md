# What does "cyber crow" actually measure?

## Overview

Ben's verdict on the best generated crow calls was "more like a cyborg, so still a little robotic but still a crow", and nothing in the project could measure that quality — the automatic bird detector had already been disqualified as a quality judge. This experiment built three cheap, interpretable acoustic measures and tested whether any of them could separate generated audio from real audio put through the same codec. The result is a null: at 40 clips per arm, none of the measures separates the model's output from the codec's, so the recorded listening test remains the only instrument that can judge "less robotic". The one solid by-product is a verified detector of codec frame-grid artefacts, which also ruled out the codec's 75 Hz frame grid as the source of the robotic sound.

## In depth

Run 2026-07-31 on `model-d384-6k`, 40 bouts per arm, American Crow, raw audio with no ambience.

### Why, and the acceptance test

BirdNET detection was at 96% of its codec ceiling, and experiment 0014 disqualified it for quality outright — a 2 kHz lowpass, audibly destroyed, retained *more* detections (0.733) than a 3 kbps codec round-trip (0.690) while sitting 3.2× further away spectrally. Fréchet distance still discriminates but is one opaque scalar that cannot say *what* is wrong. So three cheap interpretable measures were built, with the acceptance test written down first: a measure earns its place only if **real ≈ codec while generated differs from both**. Separating real from codec means it describes the tokenizer, which 0014 and 0017 already cleared; separating nothing means delete it.

### The result: a null

| measure | A real | B codec | C generated |
|---|---|---|---|
| stitch_db | **0.264** [−1.40, 1.63] | 12.567 [9.94, 13.15] | 12.902 [11.05, 14.31] |
| hnr_db | 2.555 [0.57, 3.33] | 2.590 [0.63, 3.84] | 1.827 [1.31, 2.54] |
| crest | 3.324 [2.77, 3.70] | 2.989 [2.60, 3.46] | 2.915 [2.61, 3.12] |
| voiced_fraction | 0.965 [0.84, 0.99] | 0.961 [0.81, 0.99] | 0.985 [0.98, 0.99] |
| rise_ms | 4.000 [2.00, 4.00] | 4.000 [4.00, 4.00] | 4.000 [4.00, 6.00] |
| jitter | 0.001 [0.00, 0.01] | 0.003 [0.00, 0.01] | 0.011 [0.00, 0.02] |

Medians with bootstrap intervals. Every generated value sits inside the codec arm's interval. `hnr_db` is directionally lower for generated (1.83 against 2.59) and `voiced_fraction` slightly higher, but both intervals overlap comfortably — at this n they are hints, not findings.

### The one thing that worked perfectly is the null itself

`stitch_db` was built with a null known by construction: real audio has no reason to prefer any particular codec frame phase, so it should score zero without calibration. It scores 0.264 dB (and 0.528 dB in the earlier, confounded run on entirely different audio) — the measure is sound. What it measures is also real and large: anything through EnCodec picks up a roughly 12.5 dB signature at exactly 75 Hz, the codec's own frame rate — a substantial, previously unmeasured artefact of the tokenizer. But codec and generated score 12.57 and 12.90, indistinguishable: the frame grid is entirely the codec's, and the model adds nothing detectable on top of it. Since Ben's own comparison already found the codec arm "holds up" by ear, the 75 Hz grid is demonstrably not what makes the output sound robotic, and nobody should go chasing it.

### A methodological trap, recorded because it nearly worked

The first version scored the clips the listening test plays — a bout dropped into three seconds of real ambience — and produced a clean-looking result: codec 13.4 dB against generated 7.0 dB, apparently "the tokenizer is worse than the model". That was an artefact of unequal treatment: a generated clip is codec output only where the bout is and untouched ambience everywhere else, while a round-tripped clip is codec output for the full three seconds — the codec arm simply contained more codec. With raw bouts and equal treatment the two arms land on top of each other. The lesson: an arm is not a control unless every stage that touches the audio touches it the same number of times.

`jitter` also had to be fixed mid-experiment. Integer-lag autocorrelation gives about a 3% f0 grid at 24 kHz, so every frame-to-frame change smaller than that read as exactly zero, and the first run returned 0.000 for real and generated alike — a quantisation artefact wearing the costume of a null. Parabolic interpolation on the autocorrelation peak fixed it; it still separates nothing, but it now fails honestly.

### Caveats

n = 40 per arm cannot resolve a difference the size of the HNR hint; the measures were demoted, not disproven, and a re-run at n in the low hundreds is the stated condition for believing the hint either way. All arms are drawn from the corpus, which is dominated by archive audio — these are pipeline measurements, not statements about field recordings.

### What changed

- **The timbre panel does not gate anything.** It was going to be the cheap pre-filter deciding whether a change deserved an hour of Ben's listening; it cannot do that job, and nothing should be promoted or rejected on it.
- **The codec frame grid is ruled out as the source of roboticness**, with a number: the model contributes no measurable frame-stitch beyond what the codec already puts there.
- **`stitch_db` is kept** — not as a quality measure but as a working detector of codec-grid artefacts with a verified structural zero, needing no baseline run if a future change is suspected of adding discontinuities.
- **`hnr_db`, `crest`, `voiced_fraction`, `rise_ms` and `jitter` are demoted to descriptive**, not deleted.
- **The instrument problem is not solved.** The recorded listening test remains the only thing that can judge "less robotic", which raises the value of keeping those sessions rather than throwing them away.
