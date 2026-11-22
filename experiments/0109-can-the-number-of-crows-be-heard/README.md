# 0109 — Can the number of crows be heard?

**2026-11-22** · CPU · **answer: see Results**

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

_Filled in after the run._
