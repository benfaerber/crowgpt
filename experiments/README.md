# Experiments

One question, one folder, one answer written down.

`phases/` is the plan — a programme decided in advance. This is the opposite:
the questions that come up mid-session and get answered with thirty lines of
numpy. Those answers kept evaporating. "Is my mic good enough", "is that a real
call type or the model guessing", "would a denoiser help" were each measured
properly and then lost, so the next time they came up the work started over.

## Layout

```
experiments/
  0004-snr-vs-confidence/
    README.md      the question, the method, the numbers, what changed because of it
    run.py         re-runnable, no hardcoded home directories
```

Numbered so the order is legible, slugged so the list reads as a table of
contents.

## Names you will hit that no longer resolve

Experiments 0024 through 0045 cite **PLAN-TIMBRE** by name — its work packages
(WP1, WP2), its gates, its "diagnosis point 4", its branch structure. It was
`crowgpt/PLAN-TIMBRE.md`, a plan for chasing the robotic timbre out of the
generator, and it was **deleted on 2026-08-05** along with `EXPERIMENTS.md` and
`ASK-FOR-HELP.md` — the commit calls them "the fake plans", which is the right
verdict: they asserted a programme and a summary that the folders had already
overtaken.

The references are kept rather than scrubbed because each one attributes a
specific claim — a gate, a threshold, a premise — and the attribution is how you
tell an inherited assumption from a measured one. What the plan concluded
survives in the experiments that tested it: **0028** and **0039** on whether any
codec is transparent, **0030** and **0032** on the flat-versus-ladder branch,
**0035** on filling the fine stages. Where a folder says "PLAN-TIMBRE's gate",
read it as "the gate we set before measuring" — which is exactly the thing those
experiments went on to move.

## What belongs here

An experiment, not a script. The test is whether it answers a question someone
asked, and whether the answer would be worth reading in six months. A one-off
data fix is a script; "does confidence track SNR" is an experiment.

**Write the result down even when it is boring.** A measured null — no hawk in
either recording, denoising costs more than it recovers — is worth exactly as
much as a positive one, and it is the kind nobody remembers having done.

**Say what changed.** Every README ends with what the answer altered: a
threshold, a purchase, a decision not to build something. An experiment that
changed nothing should say that too.

## Running one

Most need BirdNET or scipy, which live in the representation venv:

```
pipelines/representation/.venv-birdnet/bin/python experiments/0004-*/run.py
```

Audio comes from the field server's media directory. Override with
`FIELD_MEDIA=/path/to/media`; the default is `fieldserver/instance/media`.
That corpus is gitignored, so a result here is the durable part — the numbers
are committed, the audio they came from is not.
