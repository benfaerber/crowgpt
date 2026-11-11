# Upload policy (draft, 2026-11-10)

Status: **draft for Ben**. Nothing here is promised to anyone until he signs it
off and the app shows it before the first upload. Sections marked *Decide* are
open choices, not settled text.

Written after the first recordings arrived from outside the app: ten clips
from a London recordist who agreed to CawDex and Crow Translate but not the
generator, on the condition that they are never published. The schema now
records both (captures.provenance, captures.generator_excluded, revision
0035), so a policy that offers the same choices to app users can be kept, not
just stated.

---

## What you are sending

When you sync, the app uploads:

- **Audio** (and video, if you recorded video) of each capture you sync.
  Nothing leaves the phone until you sync.
- **Where it was**, at the precision you chose in Settings: exact GPS,
  within a few miles, or just a region you type (for example "Salt Lake
  City"). At region precision no coordinates are sent at all.
- **What you said about it**: call labels, context tags (dog nearby, food
  put down, a new crow arrived), notes, named crows and families.
- **Spoken notes**, if you dictate one, and their transcript.
- **App details**: app version, phone model, and error logs, so broken syncs
  can be fixed.

## What it is used for

Your recordings help build three things:

1. **CawDex**, a catalogue and classifier of crow call types.
2. **Crow Translate**, which pairs calls with what was happening when they
   were made. Your context tags are the most valuable part of what you send.
3. **The generator** (CrowGPT), a model that produces new crow calls.

You can say no to any of them. *Decide:* whether this is a per-account
setting (simplest, and what the schema's per-capture flag can be stamped
from at upload time) or asked per recording.

## Who sees it

- Your recordings are stored on the CrowGPT server and seen by the project's
  operators. They are not shown to other app users.
- Your exact location is never shown publicly, whatever precision you chose.
- Things built *from* the recordings (trained models, statistics, generated
  calls) may be published. They do not contain your audio or your location.

## Publishing

Recordings are **not published today**. One day, recordings made in the app
may be released as a public dataset for research. If that happens:

- Only recordings made **in the app** are eligible. Audio shared any other way
  (sent by email, a shared folder, social media) is never published.
- Location goes out at your chosen precision or coarser, never finer.
- Spoken notes and their transcripts are never published. Neither is any
  recording where people can be heard talking.
- You are credited by the name you choose, or anonymously.

*Decide:* opt-in (only recordings whose owner ticked "may be published") or
opt-out (eligible unless you untick it, with notice before any release).
Opt-in is the one nobody can later say they were surprised by.

*Decide:* the licence a released dataset carries. Ben's call when a release
is real.

## Changing your mind

- You can delete a capture from the server, or ask for your whole account to
  be removed, at any time. *Decide:* in-app button or an email to
  hello@crowgpt.org for now.
- Recordings already used to train a model cannot be removed from that model,
  but they are left out of every model trained afterwards.
- If a dataset has already been released, your recordings are removed from
  the next release.

## If this policy changes

Recordings are used under the policy that was current when you uploaded
them. A new policy applies only to what you upload after accepting it.

---

## For the code, not the app

What keeping this policy needs, beyond the text:

- Show it once before the first sync, and stamp the accepted version on the
  contributor. Captures then carry their terms from the moment they arrive.
- The generator-bound readers must filter `generator_excluded = 0`. None
  reads field audio today (crowgpt's corpus skips it), so the first one that
  does must add the filter.
- A publish exporter must filter `provenance = 'app'` plus whatever consent
  flag the opt-in/opt-out choice produces, and must drop dictations.
