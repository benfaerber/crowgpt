# Phase 5 — Put it together

> **Status: DONE — and then some.** Run it with `make field` (the demo rig it
> originally described grew into [`dashboard/`](../dashboard/) +
> [`analyzer/`](../analyzer/), served by the field server).

The original goal — **audio in → detected call → predicted category with
confidence** — works, and the dashboard goes further: it takes
audio *or video*, names the **species** (multiple at once), labels each call type
on a waveform timeline, and shows honest per-class reliability from measured AUC.
A corvid it detects but has no head for is shown species-only, never mislabeled.

Stretch goal (still open): run it live off the roof-station mic and **caption the
Poe Family in real time** — a label each time Killer or Edgar calls.
