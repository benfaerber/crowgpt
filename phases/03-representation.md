# Phase 3 — Representation

> **Status: DONE — BirdNET chosen.** The full experiment ran (below). Since
> confirmed: the "alarm/song are label-limited" call was validated when clean
> human labels lifted alarm **0.68→0.97** and song **0.59→0.91** (see
> [Phase 4](04-training.md) and [`pipelines/ingest/`](../pipelines/ingest/)).
> Pooled features nudge flight call to ~0.91.

Reuse, don't reinvent.

- **BirdNET** as a starting embedder — but note it's built for *species ID*, not
  intra-species call types, so expect to fine-tune outside its design.
- A general **pretrained audio encoder** (embeddings) may cluster call types
  better than a species tokenizer.

Try both on the Phase 0 data and keep whatever **separates the dog cluster most
cleanly**. That separation is the metric that decides the representation, and it
doubles as an early read on the Phase 0 assumption.

## First result — 2026-07-18 (classical-feature floor)

Ran a real experiment in [`pipelines/representation/`](../pipelines/representation/)
on 117 archive American Crow clips (4 call types), using classical MFCC
features as the *floor* before any learned embedder. Full write-up:
[`results/report.md`](../pipelines/representation/results/report.md).

- **Multiclass separability ≈ baseline** — silhouette −0.06, KMeans ARI 0.008,
  accuracy at the majority baseline. No cluster structure in PCA/t-SNE.
- **But per-type one-vs-rest shows real signal**: `flight call` and `alarm call`
  are individually detectable (AUC ~0.77), `song` is at chance (0.49), `call` is
  a weak catch-all (0.62). The flat multiclass number is an imbalance +
  weak-label + no-segmentation artifact, **not** the categories being identical.

Tested **call segmentation** (1,562 events, clip-grouped CV) — per-event AUC
(~0.71) was no better than whole-clip. Then tested a **learned general embedder
(AST, AudioSet-pretrained)** on the GPU — roughly a wash: macro-F1 0.36→0.48 and
it rescued `song` from chance, but no class beats ~0.74 AUC and clusters are
still absent. Everything plateaus near 0.7 AUC.

Finally ran **BirdNET** (bird-specific, 1024-dim) — the diagnostic **resolved,
and the answer is category-dependent**:

| one-vs-rest AUC | classical | AST | BirdNET |
|--|--|--|--|
| flight call | 0.77 | 0.74 | **0.89** |
| call | 0.62 | 0.55 | 0.71 |
| alarm call | 0.77 | 0.67 | 0.67 |
| song | 0.49 | 0.61 | 0.47 |

- **flight call / call were representation-limited** — BirdNET unlocks them
  (flight 0.89; first above-baseline accuracy, 0.65). **AI can distinguish these
  crow call types.**
- **alarm call / song are label-limited** — bird-specific embeddings don't help;
  fewest samples, noisiest labels. The gold set is the fix, not better models.

**Consequences for the plan:**
- **Build Phase 4 on BirdNET embeddings** for the separable classes — a simple
  classifier already beats baseline; flight-call detection is a demoable result.
- **The gold set (Poe Family, witnessed context) is the lever for the hard
  classes** (alarm, threat, song) — the project's original thesis holds.
- Retire classical features / general embedders / naive segmentation for this
  task. Embeddings cached (`results/*.npz`).
