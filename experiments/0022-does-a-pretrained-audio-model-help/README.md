# 0022 — Does a pretrained audio model help?

The FUTURE entry priced the pretrained route and argued the rental was the wrong
part of the plan: Stable Audio 3 shipped open weights in May 2026, a LoRA on the
433M `small-sfx-base` needs about 2.5 GB, and the 4070 Ti SUPER has 16. So it was
run here, for nothing, against the from-scratch model it was meant to replace.

## How it was measured

Four arms, scored identically. Two of them exist only so the other two mean
something.

| arm | what it is |
|---|---|
| `real` | held-out bouts, untouched by any model — the ceiling |
| `crowgpt` | the 18M from-scratch model of 0021 — the incumbent |
| `base` | Stable Audio 3, same prompts, **no adapter** — the control |
| `lora` | Stable Audio 3 fine-tuned on 2,961 balanced bouts — the treatment |

`base` is the arm people skip. Stable Audio has certainly heard birds, so the
prompt alone might produce something crow-shaped, and without this arm a good
`lora` number gets credited to the corpus when the phrase "American Crow alarm
call" did the work.

Every clip is trimmed to 3 s, resampled to 24 kHz and peak normalised before
scoring. BirdNET scores 3-second windows, so a 5-second generated clip would
otherwise get more chances to be called a corvid than a 2.7-second bout — a bias
running in favour of the generated arms. Normalisation matters too: Stable Audio
returns clips at peak 0.05–0.19 while the bout corpus is normalised to 0.89, and
BirdNET's confidence moves with level.

Training: rank 16, `dora-rows`, batch 8, lr 1e-4, 5 s window. **The run was cut
short at step 2000 of 3000** — a session restart killed it — so this is a
five-epoch adapter rather than the eight it was meant to be.

## The answer: it learns, and it still loses

```
                    BirdNET corvid      call-type agreement
  real                    65.0%                77.8%
  crowgpt                 71.7%                38.1%
  base                    10.8%                45.8%
  lora                    35.0%                46.7%
```

**The fine-tune plainly worked.** The control sits at 10.8% and the adapter at
35.0% — 2,961 bouts tripled the rate at which BirdNET calls the output a corvid.
Whatever else is true, the prompt alone was not doing this, which is exactly what
the `base` arm was there to establish.

**And it is still half the from-scratch model.** crowgpt reaches 71.7% against
the LoRA's 35.0%. An 18M model trained from nothing on 12.75 hours beats a 433M
pretrained model adapted to the same corpus, on the metric that asks whether the
output sounds like a crow to a crow detector.

## The result that should be distrusted

crowgpt scores **above real audio** — 71.7% against 65.0% — and that is not a
sign it has surpassed reality. BirdNET selected crowgpt's training data in the
first place: the corpus is what BirdNET called corvid at the pipeline's own
threshold. So crowgpt has been trained, indirectly, to please this exact judge,
and the metric is circular in its favour. The honest reading is that BirdNET
detection measures *how much like BirdNET's idea of a corvid* something sounds,
and crowgpt is the only arm that was optimised against it.

That does not rescue the LoRA — 35.0% is still well under real audio's 65.0%,
and the circularity cannot explain that gap. But it means the 71.7-vs-35.0
comparison overstates crowgpt's lead by an unknown amount, and the listening
test is the tiebreaker that does not share the bias.

## Call-type agreement says almost nothing here

`base` scores 45.8% while detecting a corvid in 10.8% of its clips. Those clips
are not crows, so the head is forced-choosing among four crow call types for
audio that contains none, and landing near chance-plus-prior. Read the column as
uninformative for any arm with a low detection rate rather than as evidence the
base model has call-type control. The one solid number in it is `real` at 77.8%,
which is the head working as 0021 measured.

## What changed

- **The pretrained route is viable and is not currently the better one.** It
  goes in FUTURE as tried-and-behind rather than untested. Nothing here argues
  for renting cloud compute: the whole experiment ran on the existing card, and
  the losing margin is not one more GPU-hour wide.
- **crowgpt stays the leading approach**, which promotes the question 0023 asks —
  whether that 18M model is underfit — from interesting to blocking.
- **BirdNET detection is now known to be circular for crowgpt** and should be
  reported with that caveat everywhere it appears, including the 39% and 81%
  figures in the crowgpt README.
- **Two cheap things are untested**: the adapter never finished its last 1,000
  steps, and the 1.4B `medium-base` was never tried. Both are queued.

## Re-running

```bash
# arms
cd /home/ben/Code/stable-audio-3 && uv run python \
  ../cawtalker/experiments/0022-does-a-pretrained-audio-model-help/generate.py \
  --model small-sfx-base --out .../generated-base --per_type 30
# ... and again with --lora <ckpt> --out .../generated-lora

# scoring, from the crowgpt side where BirdNET lives
crowgpt/.venv/bin/python experiments/0022-does-a-pretrained-audio-model-help/evaluate.py
```

About 12 minutes, most of it generating the crowgpt arm one bout at a time.
