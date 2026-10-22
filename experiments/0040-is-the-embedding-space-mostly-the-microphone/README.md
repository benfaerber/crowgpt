# 0040 — Is the embedding space mostly the microphone?

**2026-08-03** · 300 American Crow bouts over 60 recordings, 144 bouts over 6
species · no labels needed

## The question

Ben, on Phase 3's finding that call types form no natural clusters:

> *"I still think there is natural sound patterns. It's just the fact that maybe
> the audio is poor quality and maybe not properly normalized."*

Phase 3 measured silhouette against **call-type labels** and got ≈ 0 in every
feature space, and concluded "clusters absent". But **a silhouette of zero
against call type does not mean there is no cluster structure — it means there
is none that lines up with call type.** A space can be violently clustered by
something else and score identically.

The obvious something else is the recording. Every archive clip carries one
microphone, one distance, one gain, one background and one MP3 encoder, all
constant within a recording and different between recordings. Phase 3 could not
have detected that: its cached features carry only `X` and `y` — no recording id
— and there are **117 rows in total** across four feature spaces.

## Results

Silhouette on cosine distance. Species is the **positive control**: six species
a listener separates trivially must separate here, or the space carries nothing
and no other number in the table means anything.

| | AST (300 rows) | **BirdNET (262 rows)** |
|---|---|---|
| species — *positive control* | +0.053 | **+0.213** |
| **recording identity** | **+0.188** | **+0.296** |
| recording after per-recording CMVN | −0.226 | −0.244 |
| ratio, recording ÷ species | 3.5× | 1.4× |

**In BirdNET — the only space Phase 3 found carried anything — recording
identity organises the embedding more strongly than species does.** Not call
type: *species*. A crow against a raven against a jackdaw is a far coarser
distinction than one crow call against another, and it still loses to which
microphone was used.

So call type, being subtler than species, sits under an even larger margin of
channel. **Phase 3's measurement could not have found call-type clusters even if
they were there**, and its "clusters absent" is not evidence that they are not.
Ben's intuition was right about the diagnosis.

AST fails the control outright (+0.053) and should not be used for this question
at all — consistent with Phase 3, where it was the weakest of the three.

### But the fix he proposed is not the fix

Unsupervised k-means, silhouette of the clustering itself — the actual "do the
sounds clump" question, which needs no labels:

| k | BirdNET raw | after CMVN |
|---|---|---|
| 2 | +0.186 | +0.070 |
| 3 | +0.187 | +0.050 |
| 4 | +0.125 | +0.040 |
| 6 | +0.066 | +0.030 |
| 8 | +0.120 | +0.024 |

**There is real structure (0.19 at k=2–3), and per-recording centring destroys
it rather than revealing something better.** Normalising away the channel does
not uncover call-type clusters hiding underneath; it flattens the space.

Two readings, and this experiment cannot separate them:

- the structure genuinely *was* mostly channel, and once removed little remains;
- CMVN at five bouts per recording is too blunt — subtracting a group mean
  estimated from five samples removes a large share of real within-recording
  variation along with the channel.

The second is likely and is a design limit here, not a finding.

## What this changed

- **"Call types do not cluster" is downgraded from a result to an untested
  claim.** It was measured in a space where the microphone outranks the species,
  on 117 rows, with no channel control. That is not enough to conclude anything
  about crows.
- **Any future clustering study needs many bouts per recording and a channel
  control**, or it will rediscover the microphone and call it a call type. The
  cheapest control is the one used here: silhouette by recording id, reported
  next to whatever the study is actually about.
- **The positive control earned its place.** AST at +0.053 on species would have
  produced a confident "no clusters" that meant only "this embedder carries
  nothing". Phase 3 ran AST as one of its three spaces.
- **A footgun found on the way.** `crowgpt.birdnet.BirdNet.embed_indexed` exists
  because BirdNET returns nothing for a clip it finds no segment in — here 262
  rows for 300 clips — and its docstring says anything joining embeddings back
  to labels needs the indices. `crowgpt.embed.BirdNetEmbedder.embed` calls the
  unsafe `embed()` and discards them, so every caller of the wrapper is one short
  clip away from silently attaching labels to the wrong rows. This run uses
  `embed_indexed` directly; the wrapper should be changed or removed.
- **It does NOT show that call-type clusters exist.** It shows the previous
  measurement could not have seen them. Those are different claims and only the
  second is established.

## What would settle it

Same measurement inside the field corpus rather than the archive set: kept captures
only, many bouts per capture, silhouette by capture reported beside silhouette
by call type. There are 20 kept captures and 57 human labels on 12 of them,
which is thin — but it is one recordist, one microphone and one place, so the
channel that dominates here is nearly constant, and that is the cleanest
available test of whether the sounds themselves clump.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0040-is-the-embedding-space-mostly-the-microphone/run.py
```

About four minutes. Writes `results.json` here.
