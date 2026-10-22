# 0073 — the best longctx calls, for the gallery

**2026-08-12** · an audition, not a measurement · **answer: a shortlist on
the gallery page; Ben's ear picks for the site**

0055 re-asked for the current generator: Ben wants good CrowGPT
recordings in the gallery to update the promo site from, and the standing
best is now model-longctx at T 1.1 / k 200 (adopted after the dust
sitting) through the 0063 finetuned decoder — three upgrades 0055's
mono-v2 shortlist never had.

Same design, same honesty about it: 300 draws, instruments rank and veto,
**nothing here decides** — every automated instrument in this project has
ordered arms correctly and located nothing, so the shortlist is a
pre-filter for Ben's ear, which chooses what the site gets.

The instrument set grew with the project:

- **birdnet** ranks (max corvid confidence — inflated in absolute terms
  per 0022, fair as an ordering);
- **churn gap** vetoes the stuck-codebook artefact, as in 0055;
- **pitch strength vetoes dust** — new: clips at or below the 0069 dust
  threshold (≤ 0.41) are the bellows-wheeze failure and do not audition,
  however confident BirdNET is;
- **units** are recorded per clip (2–8 is a crow-shaped bout) and used
  for spread, so the shortlist shows sequences, not one blip five ways.

Blinding check that 0055 made mandatory: no pool is mid-flight
(dust-0069 revealed at 48/48 before this ran), and the scream page tests
a different model. Curating these clips leaks into nothing.

Licensing stance unchanged from 0055: generated audio reproduces nobody's
recording (0015: n-gram overlap 0.0x the held-out base rate at T = 1.0),
the derivative-work question for ND material stays flagged not answered,
and attribution on the page is cheap and right — Xeno-canto remains the
one source named, on the promo site only.

Published to the gallery as **`longctx-t11`** via `publish_gallery.py`.
