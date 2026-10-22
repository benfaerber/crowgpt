# Phase 2 — Labeling

> **Status: not built.** Current call-type labels come from the archives' `type`
> tags (weak) and the crow-tools human-reviewed corpus. The vision-LLM labeler
> below remains the plan for problem 2 (semantics) — unbuilt.

## Labeling strategy: tiered by how meaning is grounded

Not every call can be labeled the same way. Three tiers, easiest first:

| Tier | Calls | How it gets labeled |
|------|-------|---------------------|
| 1. Visually anchored | I see a dog, (food) | **Auto-labeled** from video: object visible in frame → label the co-occurring call |
| 2. Behaviorally anchored | Threat human vs Unknown human | Not separable by "human visible" alone — but crow **behavior** separates them. Auto-label from behavior + human-in-the-loop seed |
| 3. Social / no anchor | Come here, Where are you? | No object or behavior to see. Self-supervised clustering + my own labels |

Tier 1 is the proof of concept. Tiers 2 and 3 are the same machinery with more
anchors and manual seeding.

### Tier 2's rescue: behavior is the anchor

"Threat human" and "unknown human" both look like "human visible" to an object
detector — but the *crow's behavior* gives it away, and that behavior is visible:

- **Dive-bombing / mobbing** — the crow physically attacks or harasses.
  Unambiguous ground truth for a threat; if the crow is mobbing, the co-occurring
  call is a threat call, full stop. The threat-equivalent of "dog visible."
- Calm perching while a human passes → "unknown human."

For residual ambiguous cases, use **human-in-the-loop labeling**: the model
proposes threat/not, I correct the uncertain ones, it retrains (active learning).
Threat-vs-not is obvious to a human, so labels are cheap and clean. (This is
plain human-in-the-loop supervision, **not RLHF** — no reward model needed.)

### On the "dog visible → I see a dog" correlation

Weak supervision: video acts as an automatic labeler. It is *noisy* by design:

- The crow reacts before the dog is on camera and after it leaves — label a
  **time window** around the visual event, not a single frame.
- Sometimes a dog is visible and the crow calls about something else, or is
  silent. Those mislabels are fine **at volume**: across hundreds of events, the
  call type that *reliably* spikes is the signal; noise washes out.
- Consequence: **many examples per category** needed. Volume is the lever.

## The labeler: a vision LLM

No labeling firm. A vision-capable LLM watches the video and emits the context
label — richer than object detection (reads *behavior*, not just presence) and
removes the biggest cost and coordination headache of the project.

**Audio-gated, so it's cheap.** Don't run an LLM over every frame:

1. A cheap audio detector finds *when a loud call happened* (e.g. `t = 4:12`).
2. Only then send the LLM a **short frame sequence** (~2 s, a handful of frames —
   motion matters: "walking toward" vs "away" is lost in a single still).
3. The LLM returns **structured context**, not prose:

   ```json
   { "predator_present": true, "predator_type": "dog",
     "human_present": false, "human_behavior": null,
     "crow_behavior": "calm", "other_crows_visible": 2,
     "notes": "dog trotting across yard" }
   ```

   `crow_behavior: "mobbing" | "dive_bombing" | "calm"` anchors tier 2.

That JSON is the weak-supervision label; it feeds tiers 1 and 2 at once.

- **Human-in-the-loop seed** for tier 3 and ambiguous threat cases (active
  learning) — originally planned through an evolved `crowtracker/` UI, which was
  retired rather than evolved; the operator dashboard is where this goes now.
- **QA pass**: spot-check the LLM against my own eyes on a sample. The agreement
  rate (does its "dog"/"mobbing" match reality?) is a health check on the whole
  premise. LLMs hallucinate per-instance; trust them at volume, not case-by-case.
