# Is the embedding space mostly the microphone?

## Overview

Phase 3 had concluded that crow call types form no natural clusters in any embedding space, and Ben suspected the real problem was audio quality and normalisation rather than the crows. This experiment tested what actually organises the embedding space, using archive recordings where each recording carries its own microphone, distance, gain, background and encoder. The answer: in the BirdNET embedding — the only space Phase 3 found carried anything — which recording a clip came from organises the space more strongly than which species is calling (silhouette +0.296 vs +0.213). Since call type is a far subtler distinction than species, Phase 3's measurement could not have found call-type clusters even if they were there, so "clusters absent" is downgraded from a result to an untested claim. The proposed fix of normalising the channel away did not reveal hidden structure, however — it flattened the space.

## In depth

### The question

Phase 3 measured silhouette against call-type labels, got ≈ 0 in every feature space, and concluded "clusters absent". But a silhouette of zero against call type only means no structure lines up with call type — a space can be violently clustered by something else and score identically. The obvious something else is the recording: every archive clip carries one microphone, one distance, one gain, one background and one MP3 encoder, constant within a recording and different between recordings. Phase 3 could not have detected this, because its cached features carry only `X` and `y` with no recording id, and hold only 117 rows in total across four feature spaces.

This run used 300 American Crow bouts over 60 recordings, plus 144 bouts over 6 species, with no labels needed. Note the data is the archive corpus, so these numbers describe the pipeline's training material, not field observations of particular crows.

### Results

Silhouette on cosine distance. Species is the positive control: six species a listener separates trivially must separate in the space, or the space carries nothing.

| | AST (300 rows) | BirdNET (262 rows) |
|---|---|---|
| species — positive control | +0.053 | +0.213 |
| recording identity | +0.188 | +0.296 |
| recording after per-recording CMVN | −0.226 | −0.244 |
| ratio, recording ÷ species | 3.5× | 1.4× |

In BirdNET, recording identity organises the embedding more strongly than species does — not call type, species. A crow against a raven against a jackdaw is a far coarser distinction than one crow call against another, and it still loses to which microphone was used. AST fails the species control outright (+0.053) and should not be used for this question at all, consistent with Phase 3 where it was the weakest of the three spaces.

The fix Ben proposed — normalising the channel away — was tested with unsupervised k-means, scoring the silhouette of the clustering itself (the actual "do the sounds clump" question, needing no labels):

| k | BirdNET raw | after CMVN |
|---|---|---|
| 2 | +0.186 | +0.070 |
| 3 | +0.187 | +0.050 |
| 4 | +0.125 | +0.040 |
| 6 | +0.066 | +0.030 |
| 8 | +0.120 | +0.024 |

There is real structure (0.19 at k=2–3), and per-recording centring destroys it rather than revealing something better. Two readings, which this experiment cannot separate: either the structure genuinely was mostly channel, or CMVN at five bouts per recording is too blunt, subtracting a group mean estimated from five samples and removing real within-recording variation with it. The second is likely and is a design limit here, not a finding.

### Caveats

- This shows the previous measurement could not have seen call-type clusters. It does NOT show that call-type clusters exist — those are different claims and only the first is established.
- The BirdNET arm has 262 rows for 300 clips because BirdNET returns nothing for a clip it finds no segment in. A footgun was found on the way: `crowgpt.embed.BirdNetEmbedder.embed` calls the unsafe `embed()` and discards the indices, so every caller of that wrapper is one short clip away from silently attaching labels to the wrong rows. This run used `embed_indexed` directly; the wrapper should be changed or removed.

### What this changed

- "Call types do not cluster" is downgraded to an untested claim: it was measured in a space where the microphone outranks the species, on 117 rows, with no channel control.
- Any future clustering study needs many bouts per recording and a channel control, or it will rediscover the microphone and call it a call type. The cheapest control is the one used here — silhouette by recording id, reported next to the study's actual target.
- The positive control earned its place: AST at +0.053 on species would have produced a confident "no clusters" meaning only "this embedder carries nothing".
- What would settle the underlying question is the same measurement inside the field corpus rather than the archive set: kept captures only, many bouts per capture, silhouette by capture beside silhouette by call type. At the time of writing there were 20 kept captures and 57 human labels on 12 of them — thin, but one recordist, one microphone and one place, so the channel that dominates here is nearly constant.
