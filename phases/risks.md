# Risks / open questions

Living doc. The honest split: the **engineering** is well within reach; the
**science** (does call meaning exist and is it learnable) is the real gamble —
not a skills problem, a does-nature-cooperate problem.

> **Status update:** problem 1 (are loud call types *acoustically* separable?) is
> now demonstrated — BirdNET embeddings separate them, and clean labels push the
> hard classes past 0.9 AUC. Problem 2 (does each call *mean* something learnable?)
> is untouched and remains the central bet. Class imbalance is handled today with
> balanced class weights.

- **Is call meaning even stable?** Corvid vocalization semantics are unsettled in
  the literature. Betting on my own ear that these categories are real — Phase 0
  tests that bet cheaply. This is the project's central uncertainty.

- **Individual vs regional dialects** — calls may vary by bird or area.
  *Mitigated* by the Poe Family gold set: a single known family removes the
  cross-bird averaging that web data suffers. Still open: whether individuals
  *within* the family differ — which is why caller attribution
  (see [data-collection.md](data-collection.md)) matters.

- **Class imbalance** — "where are you?" is probably far more common than "threat
  human." Needs loss weighting or targeted collection.

- **Auto-label noise ceiling** — if "dog visible" rarely co-occurs with a
  consistent call, weak supervision fails and tier 1 falls back to hand-labeling.

- **Rare-context scarcity** — dog/threat/mobbing events are the collection
  bottleneck; they arrive on a calendar, not on demand. Continuous roof-station
  capture is the mitigation, but tier 2 will always accumulate slower than tier 1.

- **White-roof imaging** — glare/overexposure on the feeding surface; mitigated
  by a WDR camera and dawn/dusk recording. Upside: dark birds on white are a
  trivial detection target.
