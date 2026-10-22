# 0017 — Is DAC a better tokenizer than EnCodec for crow calls?

**2026-07-31** · 60 windows, 10 per species, matched bitrates and matched token counts

## The question

The model had run out of room. Experiment 0016 found American Crow at 99% of its
codec ceiling, and the paired evaluation then found the best model
statistically tied with real audio put through the same codec (−0.009
[−0.134, +0.116]). Content quality was codec-bound.

Raising EnCodec's bitrate had already failed: 12 kbps doubles the codebooks and
the model lost more to the longer sequence than the higher ceiling returned
(56% of ceiling against 96%). So the wanted thing was a codec that is *better at
the same sequence length*, and DAC is the obvious candidate — trained on
environmental audio as well as speech and music, and built specifically to fix
the codebook collapse that RVQ codecs suffer.

## Result

| arm | retain | Δconf | STFT | entropy | capacity | tokens / 3 s |
|---|---|---|---|---|---|---|
| **encodec 6 kbps, 8 cb** | **0.973** | **−0.007** | 1.151 | 9.18 | 92% | **1800** |
| dac 44 kHz, 9 cb | 0.930 | −0.008 | **1.013** | 9.70 | 97% | 2331 |
| dac 44 kHz, 7 cb | 0.483 | −0.394 | 1.253 | 9.67 | 97% | 1813 |
| dac 44 kHz, 6 cb | 0.432 | −0.561 | 1.528 | 9.54 | 95% | 1554 |
| dac 24 kHz, 8 cb | 0.378 | −0.541 | 1.381 | 9.76 | 98% | 1800 |
| dac 24 kHz, 12 cb | 0.703 | −0.166 | 1.216 | 9.81 | 98% | 2700 |

**No, and the matched-token row is the one that settles it.** At 1,813 tokens
against EnCodec's 1,800 — the only comparison where the model's job is unchanged
— DAC keeps 48% of BirdNET's detections against EnCodec's 97%, and is worse
spectrally too. DAC is only competitive when given 29% more tokens, and even
then it wins on spectral distance while losing slightly on retention.

## Why: design points, not codebook efficiency

The premise was that DAC would win on codebook utilisation. **It does, and it
does not matter.** DAC uses 95–98% of its codebook capacity against EnCodec's
92%, and is still far worse at equal sequence length.

What actually separates them is where each was trained to operate. EnCodec 24 kHz
is trained for specific target bandwidths — 1.5, 3, 6, 12, 24 kbps — so 8
codebooks at 6 kbps is a *designed* operating point. DAC 24 kHz targets 24 kbps
with 32 codebooks and DAC 44 kHz targets 9; asking either for fewer is asking
for something it was never trained to do, and the residual after the truncation
is large. The monotone collapse down DAC's rows (0.930 → 0.483 → 0.432 as
codebooks drop from 9 to 7 to 6) is that effect and nothing else.

## A correction to the reasoning that motivated this

The case for DAC leaned on 0014's measurement that EnCodec used only 74% of its
codebook capacity on crow audio, leaving a quarter unused. **That figure does not
generalise.** On these 60 windows EnCodec sits at 92%.

The difference is the sample. 0014 measured windows selected by BirdNET's
crow-positive gate — dense, loud, stereotyped calls — where the entropy is
lower. These windows are drawn at random from the recordings and are more
varied. Both numbers are correct about their own sample and only one of them was
ever a statement about the codec.

## What changed

- **DAC is off the table**, and the 2.5 hours of tokenising and training behind
  it was not spent. The gate cost about twenty minutes.
- **EnCodec 6 kbps / 8 codebooks stays**, now for a measured reason rather than
  because it was chosen first.
- **The codec is not the lever.** Together with 12 kbps failing in the full
  ladder, both directions out of the current tokenizer are now closed: more
  codebooks costs more than it returns, and a different codec is worse at equal
  cost. What remains for audio quality is the model or the objective, not the
  representation.
- **Quote capacity figures with their sample.** 74% and 92% are the same codec on
  the same species, measured over differently-chosen windows.

## Re-running

```bash
cd crowgpt && .venv/bin/python ../experiments/0017-is-dac-a-better-tokenizer-than-encodec/run.py
```
About 20 minutes. Needs `descript-audio-codec`, which pulls its weights on first
use (about 300 MB per variant).
