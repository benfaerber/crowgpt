# Outreach — PoC → video → data + money

> **Status: pending.** The technical PoC exists (now
> [`dashboard/`](../dashboard/) + [`analyzer/`](../analyzer/)); the video →
> community → data/funding flywheel below hasn't started.
>
> **Two scripts are drafted**, 2026-08-01, both written against the repo as it
> stands rather than the READMEs, which lag:
>
> - [`outreach-video-script.md`](outreach-video-script.md) — **the general cut**,
>   ~13 min, five figures, for r/crows and everyone else. Publish this first.
> - [`outreach-video-script-technical.md`](outreach-video-script-technical.md) —
>   ~22 min, every measurement kept, for HN and bioacoustics. The follow-up for
>   people who ask how it works, who arrive *after* the first one lands.
>
> Splitting them beats one script pitched between the two audiences, which is
> the version that bores everybody. Both end with the prerequisites below still
> unticked: the upload path is the one genuinely blocking, since there is no TLS
> and enrollment is a single shared secret, so the "send me your recordings" ask
> cannot honestly be made yet in either.

The growth strategy. A compelling proof of concept isn't just a technical gate —
it's the **launch artifact** that unlocks the two scarcest resources: data and
funding.

## The flywheel

```
compelling PoC  →  YouTube video  →  post to r/crows + HN/etc
      ↑                                        │
      │                                        ▼
  better model  ←  more data + money  ←  attention
```

Each turn: the demo earns attention → attention brings crowdsourced recordings
(solves the rare-context + single-family bottleneck) and small funding (extends
the $5k) → more data makes a better model → a better demo. The PoC seeds the loop.

## What makes a PoC *interesting* (not just valid)

Phase 0 has two audiences, and the same experiment serves both if you present it
right:

- **Technical:** does a distinct acoustic cluster line up with dog events? (a
  scatter plot — convincing, but nerdy and won't travel).
- **Public:** the shareable version is **"listen to these two caws — you can hear
  they're different — and here's the AI telling them apart,"** ideally building
  toward *"I point my phone at my crow and it captions what it's saying."*
  Design the PoC demo for this from the start.

## Assets you already have

- **Named characters.** Killer, Edgar, Shredder, Thrasher, Ripjaw — a fledgling
  who *calls back when you say "bye buddies."* Crow content spreads on *story*,
  and you already have one. Lean into it; it's a marketing asset, not a footnote.
- **A relatable premise** — one person, their backyard crows, and AI. That's the
  whole appeal.

## One rule: don't overclaim

The science is genuinely uncertain (see [risks.md](risks.md)). Frame honestly —
*"I'm trying to decode my crows' calls, here's my first real result"* — never
*"I decoded crow language."* Overclaiming invites backlash from ornithologists,
burns credibility with the exact community you're asking for data, and ages
badly. Honest, in-progress framing plays *better* with crow people and
researchers, and they're your data source.

## Prerequisites before the video drops

- The **upload path** (audio + video + "what happened") live and dead-simple.
- A **funding path** — Ko-fi / Patreon / small crowdfund; $5k-scale needs are
  modest, but the durable "payment" is the contributed data.
- Honest project write-up + the code, so it reads as a real open effort.
