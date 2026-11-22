# 0109 — Can the number of crows be heard?

**2026-11-22** · CPU · **answer: yes, moderately — one crow against several scores 0.80 inside a call type (95% interval 0.76 to 0.83), well above duty cycle's 0.67; it only just clears the bar set in advance**

## The question

Every contrast on the archive-remarks path so far has had the same thing
underneath it. 0107 found duty cycle is highest at roosts, so it measures the
crowd; 0106 replicated owl versus hawk without being able to say whether an
owl simply draws more birds. Until the number of birds can be estimated from
the audio, no context result can be separated from "there were more of them".

The hand-labelled American Crow segments carry a `crowCount` on every row:
1 (1,909 segments), 2 (329), 4 (248, the labeller's top bucket) and 0 (9,
dropped). That is a training set nobody has used as a target.

## Pre-registration (written before any model was fit)

**The trap.** 229 of the 248 segments counted 4 are flagged `mob`. A head
trained naively would learn "this is a mob" and be scored as if it had
learned to count. So the score that matters is taken *inside* a call type.

**Task.** One crow (`crowCount` 1) against several (2 or 4).

**Feature and model.** The 1024-d BirdNET embedding of the 3 s window that
contains the segment; `StandardScaler` +
`LogisticRegression(C=0.05, class_weight="balanced")`. Five-fold
cross-validation grouped by recordist where the corpus knows one, by file
otherwise. The model is trained on every segment, across call types.

**Primary number.** Out-of-fold ROC-AUC computed separately within each
call-type flag that has at least 30 segments on each side (expected: `mob`,
`alert`, `begging`, `softSong`, `rattle`), then averaged unweighted. 95%
interval by bootstrap over groups.

**Reading, fixed now.**
- Mean within-type AUC of 0.80 or more, every stratum's interval above 0.5:
  good enough to carry forward as a covariate.
- 0.65 to 0.80: a weak covariate, carried forward and described as weak.
- Below 0.65, or the interval of the mean includes 0.5: the number of crows
  cannot be heard this way, and 0110 goes ahead without it.

**Secondary, declared now.**
1. Duty cycle alone (0107's `U`, over the same 3 s window), scored the same
   way. If the embedding does not beat it there is nothing new here.
2. The same model scored across all segments ignoring call type — the
   inflated number, reported so the size of the trap is on record.
3. Two against four within `mob`: is there any ordering beyond one against
   several?
4. Train on segments not flagged `mob`, test on `mob` segments: does "several"
   mean the same thing across call types?

**Carried forward.** The head fit on all segments is saved under `data/` for
0110. Applied to a recording it scores the mean embedding of that recording's
crow windows. Whether that transfers to whole recordings is tested in 0110
against descriptions that state how many crows there were, not assumed here.

## Results

2,479 segments (1,903 one crow, 576 several) from 603 recordists or files.
Six call types had 30 segments on each side — the five expected and `scold`.

| Call type | One / several | Embedding AUC | 95% interval | Duty cycle AUC |
|---|---:|---:|---|---:|
| `mob` | 368 / 366 | 0.852 | 0.82 – 0.89 | 0.683 |
| `alert` | 433 / 111 | 0.821 | 0.76 – 0.88 | 0.644 |
| `scold` | 48 / 56 | 0.858 | 0.78 – 0.92 | 0.677 |
| `rattle` | 468 / 72 | 0.789 | 0.68 – 0.87 | 0.634 |
| `softSong` | 526 / 76 | 0.819 | 0.74 – 0.87 | 0.651 |
| `begging` | 231 / 73 | 0.675 | 0.56 – 0.76 | 0.701 |
| **Mean within type (primary)** | | **0.802** | 0.76 – 0.83 | 0.665 |

- **Primary: 0.802, every stratum's interval above 0.5.** By the rule written
  beforehand that is "good enough to carry forward". It clears 0.80 by two
  thousandths and only because `scold` met the 30-a-side rule; over the five
  call types the plan expected, the mean is 0.791. It should be read as a
  moderate covariate that sits on the line, not a comfortable pass.
- **The embedding hears something duty cycle does not** (0.80 against 0.67),
  in every call type except `begging`, where neither does well and duty cycle
  is slightly ahead.
- **The trap was real but small.** Ignoring call type the same model scores
  0.859, so about 0.06 of the naive number was "this is a mob".
- **There is an ordering beyond one against several.** Two against the top
  bucket, within `mob`: 0.733 (0.67 – 0.79).
- **"Several" means roughly the same thing across call types.** Trained with
  no `mob` segment and tested only on `mob`: 0.799 (0.76 – 0.83).

## Limits

- The counts are one labelling project's judgement by ear, in three buckets.
  The top bucket has no stated meaning beyond "more than two".
- A 3 s BirdNET window around a 1 s label: a second bird outside the labelled
  second but inside the window is heard by the model and not by the label,
  and the reverse.
- Everything here is Xeno-canto and Macaulay Library audio. Whether the head
  means anything on a whole recording from a phone is 0110's question.
- `begging` is the weak stratum. Several begging young sound, to this model,
  much like one.

## What it changed

- **There is now a crowd covariate.** `count_head.joblib` under
  `data/experiments/0109-crow-count/` scores one crow against several from a
  BirdNET window, and 0110 uses it to ask how much of each context is crowd.
  0107's duty cycle is retired as the crowd measure: the head beats it in
  five call types of six.
- **Not for the app.** 0.80 ranks; it does not count. Nothing here supports
  showing a number of birds to a user.
- The next context claim on this path has to report its result with the
  count score removed, or say why it cannot.
