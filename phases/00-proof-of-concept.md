# Phase 0 — Dog-call proof of concept

> **Status: not built as written.** The project delivered a *different* first
> proof — acoustic call-type classification across five corvid species (now
> [`dashboard/`](../dashboard/) + [`analyzer/`](../analyzer/), built on
> [Phase 3](03-representation.md) /
> [Phase 4](04-training.md)). The **dog / semantics** PoC described below is still
> the plan for problem 2 (meaning), pending the labeled gold set.

Prove the whole loop on **one** category before spending real money or building
infrastructure. This is the single most important phase — everything after it is
repetition.

1. Collect a small set of synchronized crow audio+video — a handful of clean
   YouTube clips now, own-camera footage later.
2. Auto-label calls in a **time window** around every "dog visible" event.
3. Embed the call audio and check: **does a distinct acoustic cluster line up
   with the dog events?**
4. If yes → the core assumption holds, proceed. If no → stop and rethink cheaply.

Target: ~30–50 clean "dog" examples + a similar count of "other" is enough to
see whether a cluster separates. Even ~20 shows a signal.

Doing this on public data first means the bet — *are these categories real and
acoustically separable?* — gets tested for a few dollars and a weekend, without
waiting on the Poe Family to acclimate.

## This PoC is also the launch artifact

It's not only a technical go/no-go — it's the demo for the YouTube video that
unlocks crowdsourced data and funding (see [outreach.md](outreach.md)). Design it
to be **legible to a lay audience**: not just a cluster scatter plot, but
*"listen to these two caws — the AI tells them apart."* Same experiment, two
audiences. Build the shareable version from the start.
