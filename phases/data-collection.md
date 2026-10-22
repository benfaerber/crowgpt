# Data Collection — kit, targets, and field protocol

> **Status: pending / in progress.** The software (corpus tooling, representation,
> training, demo) ran ahead of the physical collection below. `crowtracker/`
> exists as a *sighting* logger; evolving it into a *call* logger (an audio-clip
> table) is the key unbuilt piece for the semantics problem.
>
> **Superseded (July 2026).** `crowtracker/` was retired rather than evolved.
> `mobile/` + `fieldserver/` do this instead: a capture *is* a sighting with
> audio attached, so the note and the recording arrive together. References to
> `crowtracker/` below are kept as the record of what was planned at the time.

The project lives or dies here. Two capture modes feed two different needs, plus
a gold set that already exists in `crowtracker/`.

## How much data — count *examples per call type*, not hours

Raw hours is the wrong unit: crows are silent most of the time and the *contexts*
that matter are rare. Training a **fine-tune on a pretrained encoder** (not from
scratch) consumes labeled call instances per category:

| Milestone | Examples / category | Total | Gets you |
|-----------|--------------------|-------|----------|
| Phase 0 proof | ~30–50 of one type + similar "other" | ~100 | Show a call type forms a distinct acoustic cluster |
| Usable per-category classifier | ~100–300 | — | Model reliably tags that one call |
| Full 5-category model | ~200–500 each | ~1,500–2,500 labeled calls | The real CrowGPT |

With archive pretraining underneath, the low end of each range is realistic.

**Two very different collection problems:**

- **Common calls** (contact / "where are you", recruitment, general caws)
  accumulate fast — a few dozen hours near the family yields hundreds. Not the
  bottleneck. **~20–40 session hours** covers these and Phase 0.
- **Rare-context calls** (dog appears, threat human, mobbing) are the limiter —
  you can't schedule a dog. These come from **weeks-to-months of continuous
  capture**, not a burst of hours. A calendar problem, not an hours problem.

## Mode 1 — the roof station (continuous, unattended)

A WiFi trail cam + always-on mic at the apartment window, aimed at the flat roof
where the Poe Family is being trained to take peanuts.

> **Not to be confused with the work-roof station** designed in August 2026
> ([`roof-station.md`](roof-station.md)). This one watches birds we already know,
> from indoors, at home. That one is a *second site with a second family* and a
> recorder left outdoors on a commercial roof — so it inherits the two principles
> below (run the mic continuously and independently of the cam; WDR is the spec
> that matters) and inverts the camera choice, because WiFi on a workplace roof
> means a corporate-network conversation that cellular avoids entirely.

**What it's actually good at** (the bare roof changes the job):
- **Common-call volume** — every peanut run gives recruitment + contact calls.
- **Individual attribution** — which of the five is present/calling; builds the
  per-bird data that defuses the dialect risk. A **dark crow on a white roof is a
  trivial detection target** — easy to count/track/read posture.
- **The crow's own behavior/state** — relaxed vs alert, mobbing *if it happens in
  the airspace above the roof*.

**What it can't give:** the *cause* of an alarm. Dogs/threats happen at street
level, off-frame. The roof cam sees the crow's reaction, not the trigger — that's
a mobile-kit job (Mode 2).

**Kit:**
- **WiFi + WDR/HDR trail cam** — WiFi so footage uploads (safe from tampering,
  pullable remotely); **WDR is the one spec that matters** for a blown-out white
  roof. Aim to include the **roof edge + a sliver of sky/street** so you catch
  landings, take-offs, mobbing airspace, and occasional street context. ~$100–150.
- **Always-on 32-bit-float mic** at the window (e.g. Zoom H1essential, ~$100), or
  a USB mic into a Raspberry Pi. **This is the real payload** — audio carries the
  project on a low-context roof.
- Expect **best footage at dawn/dusk** — soft light, no glare, cooler roof, peak
  crow activity.

**Critical:** run the **mic continuously and independently** of the cam. Motion
triggers miss caws when the bird sits still. Cam = context, mic = the actual
calls; never depend on each other's triggers.

## Mode 2 — the mobile kit (sessions, walk-with-it)

For street-level rare contexts and close-range quality. Downtown SLC is loud and
theft-prone, so: directional, discreet, carryable, nothing left unattended.

- **32-bit-float handheld recorder** (Zoom H4essential/H6essential) — **can't
  clip** on sudden caws; no gain-riding while walking.
- **Shotgun mic + deadcat windscreen** — directionality beats city noise;
  proximity beats reach (lean on habituation).
- **Phone for synced video** — sync in post by aligning on a loud caw's waveform.
- Skip the **parabolic dish** — conspicuous and theft-bait in this neighborhood.

**Principles:** directionality > price; proximity > reach; crow caws sit at
~1–4 kHz (ordinary audio band — no ultrasonic gear); record continuously and
segment later; capture full-band and high-pass traffic rumble (<300 Hz) in post.

## The spoken-label trick (free ground truth)

While recording, narrate context quietly: *"dog passing, Killer alarm called"* /
*"threw a peanut, recruitment caw."* Your voice lands on the same timeline as the
caw — **automatically time-synced ground truth**. Strip/ignore your voice in post
(different band from the caws). Turns every walk into labeled gold-set data; it's
the human-in-the-loop labeling from Phase 2 done live in the field.

## The gold set — the Poe Family

`crowtracker/` already logs the family (5 named birds + roles) and a week of
sightings whose notes are proto-labels ("it caws and 4 crows come" = recruitment
with a witnessed outcome; "no alarm call upon seeing me"; "the fledgling called
back"). Roles: **your family = small, verified gold set** (trains/validates the
semantic mapping, especially threat); **web archives = volume + pretraining**.
Classic transfer-learning split: pretrain on the big noisy corpus, fine-tune and
evaluate on the small clean one.

### Evolving crowtracker into the labeling front end

It's a *sighting* logger today; to become a *call* logger it needs:
1. **An audio-clip table** linking recordings to sightings/timestamps — the one
   missing piece that makes the data trainable.
2. **Structured call-context fields** (the Phase 2 JSON: `crow_behavior`,
   `predator_present`, call-type, outcome) as real columns, so the tracker *is*
   the human-in-the-loop labeling UI.
3. **Caller attribution** — record *which* bird called, not just who was present
   (few sightings link individuals yet). High value for the dialect question.

*(Done: the old `time_of_day` Dawn/Afternoon/Dusk buckets were replaced by an
exact `observed_at` timestamp, and `perch` is now a used field.)*

## The feeding station is a data station

Training the family to a consistent roof spot builds a **repeatable recording
station**: predictable presence (high yield vs. bumping into them), a repeatable
"at the feeder" context recorded hundreds of times, and a fixed camera angle the
LLM labeler sees over and over (cleaner auto-labels). Finish the acclimation and
that one spot becomes the gold-set factory; rare contexts trickle in on the
continuous feed.
