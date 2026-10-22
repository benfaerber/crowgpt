# 0070 — does the finetuned decoder add breath off-distribution?

**2026-08-11, predictions before results** · paired decoder A/B with the
control 0069 lacked · **answer: no — the shift is uniform finetune
character, the decoder is re-acquitted, and the probe learns a caveat**

## The question

0069's decoder A/B came back not-innocent: on 29 regenerated clips, the
finetuned decoder scored −0.043 pitch strength against the frozen one — a
third of the dust-vs-clean gap, dust-ward — and flipped the dusty count
12 → 15. But 0069 had no control arm, so it cannot tell two stories apart:

1. **Off-distribution breath.** The finetune (trained on real round-trips,
   0063) behaves on generated tokens in a way its training never covered,
   and adds breathiness exactly there. Actionable: finetune v2 with
   generated grids in the mix.
2. **Finetune character.** The finetuned decoder shifts pitch strength on
   *everything*, including round-trips — in which case the probe is partly
   measuring "which decoder", 0069's A/B was contaminated, and the decoder
   is re-acquitted (0063's ears already preferred it on round-trips,
   shift or no shift).

The missing cell is round-trips through both decoders. Same probe, same
pairing, two conditions.

## Design

- **Round-trip condition:** 150 real 6 s test bouts (bouts-6s test split,
  ≤2 per recording, ≥1 s), encoded once (the finetune never touched the
  encoder), decoded through frozen and finetuned decoders.
- **Generated condition:** 150 fresh model-longctx draws at default
  sampling (T 1.0, k 200, seeds from 9000), token grids decoded through
  both.
- Per clip and condition: paired Δ = finetuned − frozen on the probe's
  features (`lib/dustprobe.py`, extracted from 0069). Wilcoxon within each
  condition; Mann-Whitney between the two conditions' Δ distributions —
  that between-conditions test is the experiment.

## Predictions (written before running)

- **Round-trip Δ pitch strength ≈ 0** (|mean| < 0.01, Wilcoxon
  non-significant): 0063's instruments and ears looked hard at round-trips
  and a periodicity shift would have surfaced.
- **Generated Δ replicates 0069**: mean ≤ −0.03, and the two Δ
  distributions separate at MW p < 0.01. That is story 1 — the finetune
  adds breath only where its training never took it.
- Named alternative: both conditions shift together (round-trip Δ also
  ≤ −0.03, distributions inseparable) — story 2, decoder re-acquitted,
  0069's A/B reinterpreted as probe contamination, and the dust hunt goes
  back to the tokens with the sampling result as the only lever standing.

## Decision rule

Story 1 confirmed → "finetune v2 trained with generated grids" graduates
to a real TODO with this experiment as its justification. Story 2 → the
probe gains a decoder-character caveat, TODO's decoder entry closes as
decided-not-to, and T 1.1 / k 200 carries the whole dust burden into the
next sitting. Either way the sitting planned in TODO.txt proceeds
unchanged.

## Result — story 2: the shift is character, not off-distribution behaviour

150 clips per condition, paired finetuned − frozen:

| condition | Δ pitch strength | Wilcoxon | dusty fine / frozen |
|---|---|---|---|
| round-trip (real) | **−0.0331** | p ≈ 0 | 48 / 34 |
| generated | **−0.0281** | p ≈ 0 | 55 / 47 |
| between conditions | — | MW p = 0.454 | — |

My prediction was wrong in the informative direction: the round-trip Δ is
not ≈ 0 — it is the *same* shift as generated, highly significant in both
conditions and inseparable between them. The finetuned decoder lowers
measured periodicity by ~0.03 on everything it touches, on-distribution
and off alike. That is finetune character — and since 0063's ears
preferred the finetuned decoder *on these very round-trips*, a −0.03
pitch-strength shift is demonstrably not an audible dust penalty. 0069's
"decoder not acquitted" was the probe reading decoder identity, not
breath.

Worth keeping from the numbers: the probe flags a third of REAL
round-tripped bouts as dusty (48/150 finetuned), which says the Youden
threshold from thirty labelled clips is aggressive, and absolute dust
rates are meaningless everywhere — only within-decoder, within-condition
orderings carry information. 0069's grid was entirely within-decoder
(finetuned) and within-condition (generated), so its ordering — and the
T 1.1 / k 200 recommendation — survives this finding untouched.

## What it changed

- **The decoder question closes as decided-not-to.** No finetune v2, no
  generated-grids retraining — the off-distribution story is dead, and
  TODO.txt's entry closes citing this experiment.
- **`lib/dustprobe.py` gains the caveat in its docstring:** pitch strength
  is decoder-sensitive (~−0.03 under the finetuned decoder), so the probe
  must never compare across decoder states; within one decoder it stands.
- **T 1.1 / k 200 carries the whole dust burden into the sitting** queued
  in TODO.txt, which proceeds unchanged.
