# 0022 — Does a pretrained audio model help?

## Overview

The project's crow-call generator is an 18M-parameter model trained from scratch, and a standing question was whether adapting a large pretrained audio model would beat it. Stable Audio 3 shipped open weights in May 2026 and a LoRA adapter fits on the existing GPU, so the comparison cost nothing to run. The answer is that the fine-tune plainly works — it tripled the rate at which a bird detector calls the output a corvid, from 10.8% for the unadapted model to 35.0% — and it still loses by half to the from-scratch model, which scores 71.7% on the same metric. The pretrained route goes down as tried-and-behind rather than untested, with the caveat that the detection metric is circular in the from-scratch model's favour, since that model's training data was selected by the same detector.

## In depth

### How it was measured

Four arms, scored identically; two exist only so the other two mean something.

| arm | what it is |
|---|---|
| `real` | held-out bouts, untouched by any model — the ceiling |
| `crowgpt` | the 18M from-scratch model of experiment 0021 — the incumbent |
| `base` | Stable Audio 3, same prompts, **no adapter** — the control |
| `lora` | Stable Audio 3 fine-tuned on 2,961 balanced bouts — the treatment |

`base` is the arm people skip. Stable Audio has certainly heard birds, so the prompt alone might produce something crow-shaped, and without this arm a good `lora` number gets credited to the corpus when the phrase "American Crow alarm call" did the work.

Every clip was trimmed to 3 s, resampled to 24 kHz and peak normalised before scoring. BirdNET scores 3-second windows, so a 5-second generated clip would otherwise get more chances to be called a corvid than a 2.7-second bout — a bias in favour of the generated arms. Normalisation matters too: Stable Audio returns clips at peak 0.05–0.19 while the bout corpus is normalised to 0.89, and BirdNET's confidence moves with level.

Training used rank 16, `dora-rows`, batch 8, learning rate 1e-4, 5 s window. The run was cut short at step 2000 of 3000 by a session restart, so this is a five-epoch adapter rather than the intended eight.

### The answer: it learns, and it still loses

```
                    BirdNET corvid      call-type agreement
  real                    65.0%                77.8%
  crowgpt                 71.7%                38.1%
  base                    10.8%                45.8%
  lora                    35.0%                46.7%
```

The fine-tune plainly worked: the control sits at 10.8% and the adapter at 35.0% — 2,961 bouts tripled the corvid detection rate, and the prompt alone was not doing this, which is exactly what the `base` arm was there to establish. And it is still half the from-scratch model: crowgpt reaches 71.7% against the LoRA's 35.0%. An 18M model trained from nothing on 12.75 hours beats a 433M pretrained model adapted to the same corpus, on the metric that asks whether the output sounds like a crow to a crow detector.

### The result that should be distrusted

crowgpt scores above real audio — 71.7% against 65.0% — and that is not a sign it has surpassed reality. BirdNET selected crowgpt's training data in the first place: the corpus is what BirdNET called corvid at the pipeline's own threshold, so crowgpt has been trained, indirectly, to please this exact judge, and the metric is circular in its favour. The honest reading is that BirdNET detection measures how much like BirdNET's idea of a corvid something sounds, and crowgpt is the only arm that was optimised against it. That does not rescue the LoRA — 35.0% is still well under real audio's 65.0%, and the circularity cannot explain that gap — but it means the 71.7-vs-35.0 comparison overstates crowgpt's lead by an unknown amount, and the listening test is the tiebreaker that does not share the bias.

### Call-type agreement says almost nothing here

`base` scores 45.8% on call-type agreement while a corvid is detected in only 10.8% of its clips. Those clips are not crows, so the classifier head is force-choosing among four crow call types for audio that contains none, and landing near chance-plus-prior. The column should be read as uninformative for any arm with a low detection rate, not as evidence the base model has call-type control. The one solid number in it is `real` at 77.8%, which is the head working as experiment 0021 measured.

### Caveats

The adapter never ran its final 1,000 steps, so the LoRA arm is undertrained relative to plan. The corvid-detection metric is circular for crowgpt, as above. The bouts are drawn from the corpus, which is dominated by archive audio; these are pipeline comparisons, not statements about field recordings.

### What changed

- **The pretrained route is viable and is not currently the better one.** It goes in FUTURE as tried-and-behind rather than untested. Nothing here argues for renting cloud compute: the whole experiment ran on the existing card, and the losing margin is not one more GPU-hour wide.
- **crowgpt stays the leading approach**, which promotes the question experiment 0023 asks — whether the 18M model is underfit — from interesting to blocking.
- **BirdNET detection is now known to be circular for crowgpt** and should be reported with that caveat everywhere it appears, including the 39% and 81% figures in the crowgpt README.
- **Two cheap things remain untested and are queued**: finishing the adapter's last 1,000 steps, and trying the 1.4B `medium-base` model.
