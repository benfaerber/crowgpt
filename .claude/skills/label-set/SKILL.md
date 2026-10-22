---
name: label-set
description: Quiz the recordist about a field capture, write down what he answers, and propose per-span call types and context chips from it. Never listens to audio — every fact comes from his answers. Use when asked what labels or chips to apply, when preparing or reviewing a labelling session, or when asked to quiz about or write up a capture.
---

# Labelling a capture, and writing its notes

Two jobs, and only these two.

1. **Propose labels** — a per-span call type and set of context chips for Ben to
   tap. You never apply them.
2. **Write the capture's notes** — into `ai_descriptions`, which is the one thing
   here you may write yourself.

Labels are proposals because they cannot be pushed server→phone: sync is
push-only, Restore fetches captures and audio only, and there is no `PATCH` route
for either, so a server-side label would strand the phone with a stale copy.

## Read first, always

```
python3 .claude/skills/label-set/capture_facts.py "<part of the capture name>"
```

A name fragment, or a bare id. It prints the capture row, what Ben typed, notes
already written, the detections with confidences, existing labels and chips, and
the live vocabulary. Refer to captures **by name** in anything Ben reads — the id
appears nowhere in the app.

If it says the vocabulary came from the database because the server was
unreachable, start it (`make field`) first. A retired key looks identical to a
live one in the database and wastes a field session.

---

# Job 1 — Write the capture's notes

## The storage already exists. Do not create any.

No column, no table, no Alembic migration, no SQL. **If you are editing anything
under `fieldserver/alembic/` or `fieldserver/src/`, stop — you have misread the
task.**

First and absolute, because it is the mistake that actually happens: a model told
"store a new kind of text" pattern-matches to *add a field* and keeps reaching
even after being told no. On 2026-07-31 one built a `debriefs` table with an FTS5
index, applied it, and when challenged rebuilt it *smaller* rather than stopping.
Both were wasted work on storage already sitting there.

## The one way in

```
# whole recording
python3 .claude/skills/label-set/write_description.py "<name>" --model <you> --stdin

# one span
python3 .claude/skills/label-set/write_description.py "<name>" --span 3.0 5.5 --model <you> --stdin
```

`--stdin` for anything with newlines, `--text` for a one-liner, `--clear` to
remove one. `--model` is recorded rather than inferred — name what wrote it and
say that it came from asking, e.g.
`fable-5 (questions put to the recordist, 2026-07-31)`.

Keyed to `(capture_id, start_sec, end_sec)`, not to a label: re-answering a call
type deletes the label and makes a new one, so anything hung off a label id dies
on a stray tap. Both NULLs mean the recording as a whole. Writing again
**replaces** that row, so read before you write or you will overwrite a paragraph
you did not know was there.

## You never listen to the audio. You ask.

**You know nothing about the sound of any recording, and you never will.** Do not
open the audio, do not describe it, do not infer what it sounds like from the
detections or the quality numbers. Every fact you write or propose comes from one
place: Ben's answers.

That is not a limitation to work around — it is the division of labour. The audio
can be re-listened to in ten years by anyone. His memory of whether the dog was
already there cannot be recovered at all, and it is going stale right now.
Measured on 2026-07-31: of 18 kept captures, 16 had no family linked — including
ones *named* "Edgar alarms on 10 story building" — and four had no written note
at all. Every one of those was known at the time.

So quiz him, and ask only what he can answer from having been there: when a
one-off event happened relative to the calls, who the humans were, how many birds
and of what age, which family, **which bird made which call**, whether a reaction
was *seen* or only inferred, whether he spoke and when. Do not ask him what a call sounded like unless he
volunteers it — that is the labelling question, and it is answered by tapping.

**Ask who called, and ask it early.** It is the most perishable fact in the
session and the only one on a label that cannot be filled in afterwards by
anybody: experiment 0017 established the audio does not carry the caller — five
crows in one recording produce the cluster structure one crow produces — so an
attribution not made now is not delayed, it is gone. Capture 103's observation
says "4 fly, Edgar watches from top of apt" in prose because there was nowhere
structured to put it; there is now.

Ask it as what he *saw*: "Could you see which bird made the call at 12 seconds —
one of the fledglings, the brood guard, a parent?" Not "was that the fledgling?",
which invites a yes.

Then record the exchange:

```
Q. When in the two minutes did the family of four fly down south into the tree?
A. Right after the first call.
```

Keep the question with the answer. An answer alone loses what was actually asked,
and the next reader cannot tell a volunteered fact from a prompted one. Then say
plainly what those answers settled, because the consequences are the part that
gets re-derived otherwise — which chip they license, which span they place an
event outside of, which question they close. Be generous: text is free, and
losing the nuance is the whole failure this prevents.

Say in the note that it came from asking rather than listening, and put it in
`--model` too. A reader a year from now must not mistake it for a description of
the sound.

## What never goes in a note

- **Not a call type.** "Alarm call" is a label and it is Ben's to give. If the
  note says it, the labelling pass reads its own output back as evidence and the
  model marks its own homework — the failure the separate table, and its
  placement *below* the detections in the dashboard, already exist to prevent.
- **Nothing about how the recording sounds.** You have not heard it. Not the
  number of voices, not whether they overlap, not the shape of a note — none of
  that is yours to say, and a sentence of it is indistinguishable from a real
  description afterwards.
- **Not his interpretation restated as an observation.** If Ben says they were
  agitated, record that he said it and keep it as his reading; the observation is
  what he *saw* — shifting, bobbing, branch-switching. His interpretations have
  their own field (`behavior_guess`) and are kept out of training on purpose.
- **Not a restatement** of the detections or of his typed description. You are
  adding what is missing, not summarising the page. Recording *why a proposal was
  made and what Ben answered* is not restatement and is worth keeping — "this
  span was flagged as most likely the adult because its crow-likeness was highest
  in the capture; he answered begging" is the reasoning of a labelling session,
  and it is otherwise re-derived from scratch every time.
- **Not a guess** about meaning, intent, or what the birds wanted.

Anything invented here returns later wearing the authority of a record. "Couldn't
tell" is a real answer and worth writing down; a number you inferred is not.

Length: a paragraph or several for the whole recording, a sentence to a paragraph
per span. One whole-recording note, plus one per span worth describing — usually
the spans with a detection, plus anything the model missed.

---

# Job 2 — Propose labels

## The table

For a capture with no labels, one row per detection in time order. For a review
of labels already applied, **only rows you would change**, plus any span with a
detection and no label:

| Span | Currently | Proposed | Caller | Context chips | Why |
|---|---|---|---|---|---|

One line of "why", and say when you are guessing. A review listing every
unchanged row buries the three that matter.

## Write it in the words on the screen

`crows_agitated` is a database key; the chip says **Crows agitated**, under a
heading that says **What the crows did**. Ben is holding the phone, not the
schema. Keys belong in verification SQL and nowhere else. Read `/api/config` for
the current text rather than trusting this — true on 2026-07-31:

- Call types: **Alarm call · Begging · Call · Flight call · Song · Mobbing ·
  Scold · Contact call · Rattle · Not a crow · Can't tell**. Note `not_a_crow`
  reads **Not a crow** and `unsure` reads **Can't tell**.
- Chip headings: **People · Animals · Food · What the crows did · Otherwise**.
  `nothing_obvious` reads **Nothing else happening**; `caller_leaves` reads
  **Caller flew off**.
- Caller roles: **Fledgling · Brood guard (yearling) · Parent · An adult, unsure
  which**. A named bird from the family roster — Edgar — is offered beside them
  and is the better answer when he can give it, because a name survives across
  recordings and a role does not.

## The rules

**Ben's own words outrank everything.** He was there and could see.

**An unconfirmed transcript is not his words yet.** A spoken note is transcribed
by a machine, and the dump prints it under its own heading with that said
plainly. It is a starting point for the quiz, never a substitute for it: speech
recognition gets proper nouns, digits and species names wrong and gives no sign
that it did — which is precisely the list you are about to ask him about. A real
one read "and they caught a lot", which is a machine's spelling of "cawed".

So the two most perishable facts, **which bird called** and **how many birds**,
must never come from a transcript alone. Quote the name or the number back to
him. A transcript he has confirmed is different and says so: it arrives as an
ordinary observation marked `[spoken in the field, confirmed]`, and by then a
human has read it and stood behind it, which is the whole difference.

**Your notes are not a second opinion.** A note you wrote and a detection are two
readings of the same evidence by two machines; they cannot corroborate each
other, and neither may stand in for an answer nobody gave. By the time you
propose, your note sits in the same dump as Ben's testimony and reads like a
record because it is one — of what a model thought, nothing more. Three failures,
likeliest first: **laundering** (a call type in a note comes back as a fact),
**outvoting** (your note says two voices, he wrote one bird — he wins), and
**filling a gap** (nobody said whether a dog was there, so a chip appears anyway
— `dog_visible` needs eyes, and only Ben has those). When a note and his words
disagree, say so in the "why" and propose his reading.

**Context is per span, not per recording.** A fact true of the whole capture
belongs in a capture field. Repeating it on every span inflates the calls ×
context matrix and adds no signal.

**A moment goes on the span containing it.** `human_gives_food`, `crow_arrives`,
`crow_departs`, `group_gathers` are events. If one happened between spans it gets
no chip and goes in the note instead.

**Name who, not just what.** The `stranger_`/`known_` pairs carry the subject.
Every human in the scene gets a chip, Ben included — the chip records the event,
`observer_role` records standing.

**Propose what was seen, not what was inferred.** `crows_agitated` needs visible
behaviour — shifting, bobbing, wing-flicking. Inferring it from angry-sounding
calls makes the co-occurrence table confirm what was put into it by hand.

**`crows_still` means "stayed put", not "calm"** — it legitimately co-occurs with
`crows_agitated`.

**Never restate a capture field as a chip.** `juvenile_present` duplicates the
juvenile count and can only disagree with it.

**A caller is only ever what he SAW.** Never propose one from the call type, from
the detections, from who was present, or from your own note. "There were two
fledglings in the capture and this is a begging call" is not seeing a bird call —
it is the arithmetic that makes an attribution worthless, and it is worse than
leaving it blank because it is indistinguishable from a real one afterwards. If
he did not watch that bird make that sound, propose no caller and say in the
"why" that nobody could.

**Blank is a real proposal.** Most spans will have none. A label with no caller
means nobody looked, and that must stay different from "nobody was there" — a
table where every row is filled in is a table somebody guessed in. Do not treat
an empty Caller column as work left undone.

**"An adult, unsure which" beats a guess between parent and brood guard.** They
are hard to tell apart at twenty metres and the vocabulary has a value for
exactly that. Proposing `parent` when he said "one of the adults" invents the one
distinction the whole field exists to capture — León's breeder-versus-helper
axis — and it invents it in the direction that looks like data.

**A name outranks a role when he can give one.** Edgar is on the roster; the two
parents are not. `crow_id` survives across recordings and lets "does this bird
always call this way" become a question; `caller_role` does not. Ask for the name
first and fall back to the role.

**Never backfill a caller from an old capture.** If a session is reviewing
recordings from weeks ago, propose no callers at all unless he volunteers one
unprompted and says he remembers watching it. `attributed_at` records when the
attribution was made precisely so a late one is visible — do not create rows that
make that column lie.

**Candidates deserve the most attention.** A low `crow_conf` marks the faint
awkward calls the model is worst at. `not_a_crow` is a real answer and a negative
example nothing else produces; `unsure` beats a guess. But ask before assuming —
a 0.18 that Ben confirms is a real alarm is worth more than a clean one.

**Find Ben's voice before it is labelled as a crow.** He talks to them on
purpose; his voice is the experiment, not noise in it, so never suggest he stay
quiet. Two failures: the detection *is* his voice (`not_a_crow`; a low
`crow_conf` under a confident call type is the tell), or a real call **and** his
voice share the span — both true, the label right, the clip carrying a human
saying "hi crow". Span edges cannot be trimmed, so the note is the only place
that can be recorded.

**Never propose a key absent from the printed vocabulary.** The server rejects
inactive keys with a 400, which surfaces on the phone as red text.

## Where the taps go

Open the capture, tap the **Label calls** card (it reads `0 of 7`). The deck is
one card per detection; the strip at the top jumps to any card, amber for an
undecided candidate. Each card has **▶ Play this call**, then **What was it?**
and the call-type buttons. **Chips only appear after a call type is chosen.** The
deck does not advance by itself — swipe when the chips are done. **Retract this
label** is the undo.

Warn him, per handover:

- **Never re-tap a call type, including one already ticked.** It is
  destroy-and-recreate and cascades away every chip on that span, server-side
  too. The ✓ makes a second tap look like a toggle-off; it is not, and nothing on
  screen says the chips went. If a call type must change it goes **first**, and
  the chips are re-applied after.
- **A re-tap does not touch the note** — that survives, keyed to the seconds.
- **Stay on the network.** Adding a chip is queued; removing one fires
  immediately and is swallowed if it fails.
- **Span edges cannot be changed.** A coarse span stays coarse; the real timing
  goes in the note.
- **New vocabulary needs an app relaunch, not a Sync** (`refreshConfig` runs once
  per launch).

**The caller picker is under the call-type buttons**, on the same card, and only
appears once a call type is chosen. Its rules on screen match the ones above:
nothing is preselected, there is no "unknown" button, and tapping the chosen
role again clears it. So a blank picker is a finished answer, not an unfinished
one — do not tell him a card is incomplete because it has no caller.

- **Setting a caller does not destroy the label.** Unlike a call type, it is a
  patch, so the context chips survive. He can add or change it after the chips
  are on, and after a sync.
- **It works offline.** The answer is written locally and travels with the label
  on the next push; a caller added to an already-synced label is sent
  immediately when there is signal and queued when there is not.
- **A named bird is not on the phone yet.** The roster exists server-side and
  holds Edgar, but the card offers roles only. If he names a bird, put the name
  in the span's note in prose — not as a key — and say in the write-up which
  spans have a name waiting.

## Afterwards

```sql
SELECT l.capture_id, l.id, l.start_sec || '-' || l.end_sec AS span, l.call_type,
       group_concat(ce.key, ' + ') AS context
FROM labels l LEFT JOIN context_events ce ON ce.label_id = l.id
WHERE l.capture_id = <id> GROUP BY l.id ORDER BY l.start_sec;
```

A label id higher than before means a call type was re-tapped and that span's
chips were cascaded away. Notes are checked separately, since nothing above
touches them:

```sql
SELECT coalesce(start_sec || '-' || end_sec, 'whole') AS span, model, written_at,
       length(description)
FROM ai_descriptions WHERE capture_id = <id>
ORDER BY start_sec IS NULL DESC, start_sec;
```
