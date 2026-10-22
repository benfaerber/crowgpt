# 0017 — Is DAC a better tokenizer than EnCodec for crow calls?

## Overview

The crow-call generator turns audio into discrete tokens with a neural codec, and previous work had shown the model's quality was limited by that codec rather than by the model itself. This experiment asked whether swapping the codec — from EnCodec to DAC, a newer codec designed to use its codebooks more efficiently — would raise that ceiling without making the token sequences longer. The answer is no: at a matched token count, DAC kept only 48% of the bird-detector's detections against EnCodec's 97%, and DAC was only competitive when given 29% more tokens. EnCodec at 6 kbps stays, and the codec was ruled out as the lever for further quality gains.

## In depth

### The question

Run on 2026-07-31 over 60 windows, 10 per species, at matched bitrates and matched token counts. Experiment 0016 had found American Crow at 99% of its codec ceiling, and the paired evaluation found the best model statistically tied with real audio put through the same codec (−0.009 [−0.134, +0.116]) — content quality was codec-bound. Raising EnCodec's bitrate had already failed: at 12 kbps the codebooks double and the model lost more to the longer sequence than the higher ceiling returned (56% of ceiling against 96%). So the wanted thing was a codec that is better *at the same sequence length*, and DAC was the obvious candidate — trained on environmental audio as well as speech and music, and built to fix the codebook collapse that RVQ codecs suffer.

### Result

| arm | retain | Δconf | STFT | entropy | capacity | tokens / 3 s |
|---|---|---|---|---|---|---|
| **encodec 6 kbps, 8 cb** | **0.973** | **−0.007** | 1.151 | 9.18 | 92% | **1800** |
| dac 44 kHz, 9 cb | 0.930 | −0.008 | **1.013** | 9.70 | 97% | 2331 |
| dac 44 kHz, 7 cb | 0.483 | −0.394 | 1.253 | 9.67 | 97% | 1813 |
| dac 44 kHz, 6 cb | 0.432 | −0.561 | 1.528 | 9.54 | 95% | 1554 |
| dac 24 kHz, 8 cb | 0.378 | −0.541 | 1.381 | 9.76 | 98% | 1800 |
| dac 24 kHz, 12 cb | 0.703 | −0.166 | 1.216 | 9.81 | 98% | 2700 |

The matched-token row settles it. At 1,813 tokens against EnCodec's 1,800 — the only comparison where the model's job is unchanged — DAC keeps 48% of BirdNET's detections against EnCodec's 97%, and is worse spectrally too. DAC is only competitive when given 29% more tokens (the 9-codebook, 2,331-token row), and even then it wins on spectral distance while losing slightly on retention.

### Why: design points, not codebook efficiency

The premise was that DAC would win on codebook utilisation. It does, and it does not matter: DAC uses 95–98% of its codebook capacity against EnCodec's 92%, and is still far worse at equal sequence length. What actually separates the codecs is where each was trained to operate. EnCodec 24 kHz is trained for specific target bandwidths (1.5, 3, 6, 12, 24 kbps), so 8 codebooks at 6 kbps is a designed operating point. DAC 24 kHz targets 24 kbps with 32 codebooks and DAC 44 kHz targets 9 codebooks; asking either for fewer is asking for something it was never trained to do, and the residual after truncation is large. The monotone collapse down DAC's rows (0.930 → 0.483 → 0.432 as codebooks drop from 9 to 7 to 6) is that effect and nothing else.

### A correction to the motivating reasoning

The case for DAC leaned on experiment 0014's measurement that EnCodec used only 74% of its codebook capacity on crow audio. That figure does not generalise: on these 60 windows EnCodec sits at 92%. The difference is the sample. 0014 measured windows selected by BirdNET's crow-positive gate — dense, loud, stereotyped calls, where entropy is lower — while these windows were drawn at random from the recordings and are more varied. Both numbers are correct about their own sample, and only one of them was ever a statement about the codec.

### Caveats

The 60 windows are drawn from the training corpus, which is dominated by archive audio rather than field recordings; the retention and spectral numbers describe how the codecs treat that corpus, not crow vocalisation in general. The gate itself cost about twenty minutes to run.

### What changed

- **DAC is off the table**, and the roughly 2.5 hours of tokenising and training it would have taken was not spent.
- **EnCodec 6 kbps / 8 codebooks stays**, now for a measured reason rather than because it was chosen first.
- **The codec is not the lever.** Together with 12 kbps failing in the full ladder, both directions out of the current tokenizer are closed: more codebooks costs more than it returns, and a different codec is worse at equal cost. What remains for audio quality is the model or the objective, not the representation.
- **Quote capacity figures with their sample.** 74% and 92% are the same codec on the same species, measured over differently-chosen windows.
