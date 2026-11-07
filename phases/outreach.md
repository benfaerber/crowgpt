# Outreach

The plan for getting CrowGPT in front of people, rewritten 2026-11-06 around what
the first attempts showed. It assumes about 3 to 5 hours a week, because this is
one person's evenings. Anything that needs more than that gets cut, not squeezed.

## What it is for

**More recordists, then more attention.** The number that limits the project is
human-labeled call audio with a witnessed situation, so the measure of outreach is
people outside the backyard sending recordings. Stars and visits only matter if
they lead there.

The first-pass goals below are guesses rather than forecasts, set so a review has
something to compare against.

| By | Goal |
|---|---|
| 2026-12-15 | One launch done, 50 people following, 2 expert conversations |
| 2027-01-31 | 3 to 5 outside recordists with kept captures, one video out |

Baseline, 2026-10-30 to 11-05: 41 visitors, 152 page views, 6 GitHub stars, one
active recordist.

## The story

**One person, one home GPU, one crow family, and a real attempt at the hardest
version of the question.** Confident on purpose. Solo work with almost no money is
the appeal, and the ambition is stated as an ambition.

The evidence, all checkable: 94 written-up experiments including the nulls, an
18.7M-parameter model trained at home, a demo anyone can press, and open code.

Two limits keep it credible:

- **Ambition is fine, false results are not.** "I'm trying to talk to crows" is
  bold. "I decoded crow language" is untrue, and no call has been translated yet.
- **Do not lead with the 433M comparison.** It rests on the circular BirdNET score
  and an earlier model. It is a footnote, always with its caveat.

## Who, in order

1. **Technical and curious readers.** They enjoy the solo story and do not need the
   app to be ready. This buys credibility and collaborators.
2. **A short, hand-picked list of experts and serious recordists,** written to one
   at a time. Few people, high value, and their critique is useful in itself. The
   list stays out of this repo.
3. **Birders and crow people,** once there is a finding about crows to lead with.
   Lead with the crows and disclose the AI plainly. Never hide it.

General crow forums are not a channel for now: an AI-led post met flat refusals in
2026-11, and the project does not need to win that argument to reach its goal.

## The funnel, and the gap in it

Attention, then a way to stay in touch, then an invite. The middle step does not
exist yet: a visitor who likes the page can request the app or leave. A launch
without somewhere to follow is mostly wasted, so **one email list comes first**,
sending one short field note a month.

## Schedule

### Before anything public, by 2026-11-20

Launch blockers:

- [ ] Check the licences on the two stock assets (skyline, crow flight sprite), or
      replace them. See the promo push entry in `FUTURE.txt`.
- [ ] Put Cloudflare in front of `field.crowgpt.org` with a rate limit on
      `/api/demo/` and Turnstile on the buttons. The demo shares a box with real
      field uploads, so a spike must not be able to touch them. Daurian's
      2026-11-06 code/audit is in `fieldserver/deploy/cloudflare.md`; rollback is
      written, but widget setup, promo deploy, enforcement, dashboard rules,
      proxy flip and full Pixel 8 verification are still pending. Direct origin
      access and shared CPU/memory remain unresolved isolation risks; keep this
      blocker open, and never change the firewall without Ben's explicit OK.
- [ ] Add the email list to the page, on the Resend setup that already sends invites
      (`core/mail.py`). Bulk mail needs an unsubscribe link and a postal address,
      which one-to-one invites do not. People who only requested the app did not
      sign up for news, so they are not added without asking.
- [ ] Make the invite say plainly that captures carry precise GPS, until they are
      coarsened. Recordists may be standing at home.
- [ ] Retake the "Cawtalker" screenshot.
- [ ] Settle the open copy questions: which model takes call types, the audio line
      in the footer, whether the fledglings are still fledglings, and how
      "conversation" fits with no playback.
- [ ] Push the repo and the corrected Hugging Face card.
- [ ] Add GitHub topics and a description a stranger can read.

Cheap wins:

- [ ] Ask the person who coined "the DeepSeek of animal communication" whether it
      can be quoted, with their name.
- [ ] Ask the people who emailed about Gemini what they typed.

### Quiet review, 2026-11-14 to 11-30

Write to 5 to 10 people on the private list, one at a time, asking what is wrong
with the work. Fix what they find before the launch.

### Show HN, Tuesday 2026-12-01 or Wednesday 12-02

Avoid Thanksgiving week. Post in the US morning and clear the day to answer
comments in the first person. One post, no asking anyone for votes. Follow-up
posts to ML and bioacoustics communities only after checking each one's rules.

### Review, 2026-12-15

Run `make -C promo traffic` within a week of the launch, since the detail expires.
Compare against the goals above, and decide:

- **Requests came in:** send invites and support those recordists first. Their
  captures are the point.
- **Attention but no recordists:** move the time to individual outreach.
- **Nothing happened:** the story or the title missed. Rework it and try one
  different channel before making anything expensive.

### One video, January 2027

Rework [`outreach-video-script.md`](outreach-video-script.md), which predates
CrowGPT2 and the hosted server. Long deep-dives on one obsessive project suit this
audience, and it is the largest piece of work here, so it comes after the launch
has shown which parts of the story land. The
[technical script](outreach-video-script-technical.md) is held for whoever asks.

### Throughout

- One field note a month to the list.
- One short clip a week on the existing Instagram, real recordings of the family.
  Thirty minutes, and it can skip a week without harm.

## The next big moment

The best story still to come is the first call mapped to a witnessed meaning. That
is when to approach science writers, local news, the local Audubon chapter and
birders, because it is a finding about crows rather than a tool. Save those for it.

## Not doing

- **Ads, or buying any attention.** Nothing yet to convert it into.
- **Alt accounts or seeded comments.** One discovery ends the project's credibility.
- **A Discord or forum.** An empty room looks worse than none. Revisit at 20 active
  people.
- **LLM citation monitoring.** See `FUTURE.txt`.
- **A funding page before the launch.** Asking for money with six stars reads badly.
  Revisit once people ask how to support it.
- **Posting everywhere.** One channel done well, in the order above.
- **A Google Play listing.** Invites suit a handful of recordists, and a listing
  would cost more than it brings at this stage. See the Play entry in `FUTURE.txt`.

## Scoreboard

Fill in one row after each push.

| Date | Push | Views | Visitors | App requests | List | Active recordists |
|---|---|---|---|---|---|---|
| 2026-11-05 | Baseline | 152 | 41 | | 0 | 1 |
