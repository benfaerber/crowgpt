# Is the interference wind, or traffic?

## Overview

Capture 87 has continuous broadband noise from ~13 s to the end that had twice been described as "vehicle or wind" without checking — and the two call for different money: wind means a $15 furry windshield, traffic means a directional microphone or a different place to stand. Band-energy analysis showed the wash is traffic, not wind: the low frequencies barely move while the energy piles up at 1–4 kHz, which is the crow band, and holds steady rather than gusting. A later amendment (2026-08-02) notes that while the measurement stands, the conclusion "a windshield buys nothing" overreached — no experiment in the project has ever sampled a windy day, and the windshield stays on in practice.

## In depth

### Method

Compare band energy during the wash against a calm stretch of the same recording. Wind on a microphone is overwhelmingly sub-200 Hz, gusty over seconds, and structureless. Traffic reaches further up the spectrum and is steadier.

### Results

| band | wash vs calm |
|---|---|
| 0–100 Hz | +1.5 dB |
| 100–200 Hz | +0.7 dB |
| 200–500 Hz | +1.8 dB |
| 500–1000 Hz | +4.5 dB |
| **1000–4000 Hz** | **+7.1 dB** |
| 4000–12000 Hz | +1.4 dB |

Sub-200 Hz moved 6.4 dB peak-to-trough across nine seconds, with a gust ratio (std/mean) of 0.26 — steady, not gusty.

**Not wind.** Wind would have loaded the bottom two bands and left the rest alone. This does the opposite: the low end barely moves and the energy piles up at 1–4 kHz, which is the crow band, and holds steady.

### What it changed

At the time, a windshield was dropped from the shopping list, and the case for directionality was strengthened on geometry rather than on specification. The interference sits in the same band as the calls, so it cannot be filtered out after the fact; but it arrives from street level while the bird is on a roofline. Those are far apart in angle, which is the one situation where a modest supercardioid earns its money — its rejection is strongest 120–150° off axis, and pointing up at the roof puts the road behind and below it. It also made a free improvement obvious: standing with a building between the microphone and the road buys dB for nothing.

Experiment 0004 ([0004](../0004-snr-vs-confidence/)) gives what those dB are worth — roughly 0.19 of BirdNET confidence per 2.5 dB in this range.

### Amendment, 2026-08-02 — the shopping-list line overreached

"Dropped a windshield from the shopping list" was drawn from one wash in one capture on one day, and it does not generalise. The measurement is fine: in capture 87's 13–22 s wash the energy piles up at 1–4 kHz and the low end barely moves, which is traffic and not wind. What was wrong is the leap from *that wash was traffic* to *a windshield buys nothing here*.

No experiment in this project has ever sampled wind. Experiment 0010 went on to test the windshield and said so explicitly — gustiness of the sub-200 Hz band was 1.07/0.78 without and 1.05/0.80 with, "unchanged", because there was no wind to remove on those days either. So the two experiments that touch wind protection both ran in calm conditions, and neither can speak to the case the windshield is for.

Ben's observation from field sessions since: without the guard it is constant wind and road noise together; with it, passing traffic reads as discrete swells instead of a wall. That is mechanistically exactly what a furry windshield does — it attacks turbulence at the capsule, which is broadband and fills the gaps, and does nothing to distant traffic, which is what stays behind as separable events. His observation is not in tension with this experiment's numbers; it is about a condition this experiment never recorded in.

The standing advice is unchanged in practice — keep the windshield on (experiment 0010) — but the reason recorded here was wrong, and experiment 0001's "wind protection before either" was never actually tested. TODO.txt carries the A/B that would settle it, which needs a windy day rather than a better analysis.

A pattern worth naming, because it has now happened twice: a correct measurement whose conclusion gets generalised past the conditions it was made in. Experiment 0017's rejection of DAC was the other one — right about retention at matched token count, wrong the moment that constraint expired.
