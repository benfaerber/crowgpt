# Video script — "I tried to understand what my crows are saying"

2026-08-01. **The general cut** — the concepts, not the numbers. Target
**12–13 minutes**, and the one to publish first.

The deep version lives in
[`outreach-video-script-technical.md`](outreach-video-script-technical.md):
same spine, ~22 minutes, every figure kept, aimed at HN and bioacoustics rather
than r/crows. It is the follow-up for whoever asks how it works in the
comments — not an alternative to this one.

The rule from [outreach.md](outreach.md) still holds — *"I'm trying to decode my
crows' calls, here's my first real result,"* never *"I decoded crow language."*
Draft 1 tried to earn that with tables. This one earns it by saying it.

Almost no figures survive. The ones that do are there because they're *vivid*
(eighteen real recordings, one dog, ten times out of thirty), not because
they're evidence. Evidence lives in the repo, and the description links to it.

**Working title:** *I Tried to Understand What My Crows Are Saying*
**Backup:** *Can AI Translate Crows? I Spent Two Weeks Finding Out*

`[VISUAL]` = what's on screen. `>` = spoken. `[TEXT]` = overlay.

---

## COLD OPEN — 0:00

`[VISUAL]` Black. Play one caw. Then a very different one.

> Those are both crows. Same species. Same family of birds, in my backyard,
> forty feet from my back door.
>
> One of them is an alarm call. The other one isn't.
>
> If you can't hear the difference — same. I couldn't either, for about a week.

`[VISUAL]` Laptop. A recording plays, and coloured blocks appear along the
waveform as it goes, each labelled — *flight call*, *alarm call*, *call*.

> This is software I built. It listens to a recording, finds every crow in it,
> works out what species it is, and labels what *kind* of call each one was.
>
> It runs on my laptop. It took about two weeks of evenings.

`[VISUAL]` Photo of Edgar.

> This is Edgar. He's a young crow who hangs around helping his parents guard
> the nest instead of going off and starting his own family. He's one of five
> birds this whole thing exists for.
>
> Now — the honest bit, right at the top, so nobody has to sit through nine
> minutes waiting for it.

`[TEXT]` **I have not decoded crow language.**

> I haven't. Nobody has. What I built can tell you what a call *sounds like*. It
> cannot tell you what it *means*. Those turn out to be completely different
> problems, and today only one of them works.
>
> This video is about the one that works, the one that doesn't, and the several
> times I nearly convinced myself of something that was flatly untrue.

`[VISUAL]` Title card.

---

## PART 1 — THE TWO QUESTIONS (1:15)

`[VISUAL]` Simple animation: one question mark splits into two.

> The thing that took me way too long to figure out is that *"what is the crow
> saying"* isn't one question. It's two, and they need totally different
> approaches.

`[TEXT]`
```
1. What are the different calls?   →  can a machine hear the difference?
2. What does each one mean?        →  needs someone standing there watching.
```

> Question one is: are crow calls even sortable into types? Can a machine tell
> them apart at all? That's a normal computer problem. You need recordings, and
> you need someone to have written down what each one was.
>
> Question two is: does *this* call mean "there's a dog"? And you can never get
> that from audio alone. Not with a million hours. Because the recording doesn't
> contain the dog. Somebody has to have been *there*, watching, and written it
> down at the moment the bird called.
>
> Keeping those two apart is basically the whole design of this project.

`[VISUAL]` The five crows as a family card, with photos where they exist.

> The birds are the Poe family. Two parents, two fledglings, and Edgar. Yes, I
> named them. No, I'm not defending the naming scheme.
>
> One of them calls back when I say "bye buddies." That's not evidence of
> anything. It's just why I started.

---

## PART 2 — TEACHING A COMPUTER TO HEAR A CROW (2:45)

`[VISUAL]` A waveform. Then it dissolves into a grid of numbers.

> Here's the core idea, and it's genuinely the whole trick.
>
> A computer can't work with sound directly — it's just a huge wall of numbers.
> So the first job is turning a sound into a **fingerprint**. A short summary,
> where two sounds that are *similar* end up with *similar* fingerprints.
>
> Get the fingerprint right and the rest is easy. Get it wrong and nothing else
> you do matters.

`[VISUAL]` Three doors, opened one at a time.

> I tried three.
>
> **First, the classic approach** — the standard way of measuring audio, the one
> in every textbook. Built for human speech, decades old.

`[VISUAL]` A scatter plot that is just a single formless blob.

> That's what it gave me. Every call type sitting on top of every other call
> type. That's a picture of learning absolutely nothing.
>
> **Second, a general-purpose AI** trained on millions of everyday sounds —
> traffic, dogs, doors, music. Better! Still not usable.
>
> **Third — and this is the one — a model called BirdNET**, from Cornell. It's
> been trained on millions of bird recordings and nothing else. Telling birds
> apart is the only thing it has ever done.

`[VISUAL]` The blob resolves into visible clusters.

> And suddenly the calls separate.
>
> Which makes sense in hindsight. A general audio model has to keep track of
> whether something is a guitar or a truck. BirdNET spent its entire existence
> obsessing over tiny differences between bird noises. It already knew what to
> pay attention to.

`[TEXT]` **Lesson 1: a specialist beats a generalist.**

### But it only half worked

`[VISUAL]` Four call types listed. Two go green. Two stay red.

> Except — it only fixed *half* the call types.
>
> Two of them got dramatically better. Two of them didn't budge.
>
> And my first instinct was "well, BirdNET's unreliable then." Which was wrong,
> and figuring out *why* it was wrong is the most useful thing I learned in the
> whole project.

`[VISUAL]` Two boxes.

`[TEXT]`
```
Sometimes the machine genuinely can't hear the difference.
Sometimes the machine hears fine — and you told it the wrong answers.
```

> Those look identical from the outside. Both of them just look like "it doesn't
> work."
>
> My recordings came from a public archive where volunteers upload bird audio
> and type in a text box what they think the call was. Which is generous and
> wonderful and *extremely* loose. If a big chunk of things labelled "alarm
> call" aren't actually alarm calls, then no amount of clever software will ever
> fix that. You're teaching it from a textbook with wrong answers in the back.
>
> So the problem might not be the AI. The problem might be me.

### The part that isn't mine

`[VISUAL]` A GitHub page. Hold on it. Let it be a beat.

> And I could actually test that, because somebody else had already done the
> single most tedious job imaginable.
>
> This is a project called crow-tools. Somebody sat down and listened to
> **several thousand seconds of crow audio, one second at a time**, and wrote
> down what every single one was. By hand. Then they put it on the internet for
> free.
>
> The project's abandoned now. I've copied the labels into mine so they don't
> disappear when the repo does, with credit, under their licence.

`[VISUAL]` Before/after bars. No numbers on screen — just the bars jumping.

> Same software. Same fingerprints. Same everything. I only swapped the labels.
>
> The two call types that had been stuck? Both jumped to *working*. All of them
> did.

`[TEXT]` **Lesson 2: better labels beat better AI.**

> I want to be really clear about this bit, because the biggest single result in
> this project **is not mine.** It came from one person doing thousands of
> seconds of listening for free, and putting it somewhere I could find it.
>
> That's the actual state of AI, by the way. Everyone talks about models. The
> thing that's usually broken is the data.

---

## PART 3 — GOING OUTSIDE (5:15)

`[VISUAL]` Outside. Phone in hand. Real crows.

> Right. So the classifier works. Which means the problem immediately moved
> somewhere much less fun.
>
> To answer question two — what calls *mean* — I need recordings of *my* crows,
> with notes about what was actually happening. And downloaded audio can't do
> that, because it doesn't come with a witness.
>
> So I had to go outside. Which, as a software person, I'd been putting off.

`[VISUAL]` Screen recording of the app: hit record, waveform moves, stop, the
capture appears in a list.

> I built a phone app. It records, it tags where you are, and it lets me mark up
> the calls afterwards.

`[VISUAL]` Two waveforms: a clean one, and a mangled one.

> One thing surprised me here. Your phone doesn't record what the microphone
> hears. It cleans it up first — boosting quiet bits, cutting background noise —
> and all of that is tuned for **human speech on a phone call.**
>
> Point that at a faint bird call two hundred feet up, and the phone decides
> it's noise. And politely deletes it.
>
> So the app has to go around all of that and ask for the raw microphone. Which
> phones will let you do — but mine both officially claim they *can't*, and then
> just do it anyway when you ask. So the app doesn't trust what the phone says
> about itself. It asks, then checks what it actually got.

`[TEXT]` **Lesson 3: don't trust a device's own paperwork.**

`[VISUAL]` The dashboard. Drag an audio file onto it. Watch calls appear along
the waveform.

> Everything syncs to a small server, which runs the analyzer, and gives me this
> — a page where I can go through recordings, hear what the model heard, and
> correct it.
>
> And that's where the real work happens. Three different kinds of note, kept
> carefully separate:

`[TEXT]`
```
What the bird said.          ← the only thing that teaches the model
What I saw at that moment.   ← attached to the CALL, not the recording
Anything else I noticed.     ← free writing, for things I don't have a word for yet
```

> That middle one has a trap in it that I fell straight into.
>
> If you tag the whole *recording* with "a dog walked past," and there are ten
> calls in that recording, you've just told the computer that all ten of them
> were about the dog. Even the ones from four minutes later. Do that for a year
> and your data will confidently tell you crows sing at dogs.
>
> So every note has to attach to one specific call. It's a small thing that
> would have quietly poisoned everything.

`[VISUAL]` A button in the app that says "by ear."

> One more, because I like it. There's a button to mark a call the model
> *completely missed*.
>
> Sounds minor. It's not. The model is genuinely bad at hearing baby crows
> begging — it barely registers them. So if I only ever confirmed calls it
> already found, I could only ever collect more of what it's already good at.
> The stuff it's worst at could *never* improve. Its blind spots would be
> permanent, forever.

### Where I actually am

`[VISUAL]` The dashboard stats. Slow.

> Okay, so. Let me show you the numbers, and they are small.
>
> I've got a bit over a hundred recordings in the system — but most of those are
> downloaded archive clips and the same test file uploaded eleven times, because
> that's how you check software works.
>
> Recordings of real crows that I was actually standing next to?

`[TEXT]` **Eighteen.**

> Eighteen. That's it. That's the corpus.
>
> Which is why anything I show you that counts *all* the recordings is a fact
> about my software, not about crows. The dashboard actually labels which one
> it's showing you, because I kept confusing myself.

`[VISUAL]` The calls-and-situations grid. Zoom slowly to one cell.

> And here's the grid this whole project exists to fill in. Every call I've
> labelled, against what I saw happening at the time.
>
> Now. The original plan for this entire project — written before I'd built a
> single thing — was: *do crows have a specific call for dogs?*
>
> After two weeks, the number of dogs in my data is...

`[VISUAL]` The cell reads 1.

> One. One dog.

`[VISUAL]` Beat. Let it sit.

> And that's the real lesson of going outside. I can't schedule a dog.
>
> This isn't a "grind for a weekend" problem. It's a *calendar* problem. You
> can't make a hawk fly over on a Tuesday because that's when you're free. You
> just have to be recording when it happens.

`[TEXT]` **Lesson 4: you can't schedule a dog.**

---

## PART 4 — MAKING A CROW NOISE (8:00)

`[VISUAL]` Tone shift. Play a generated caw.

> Okay, serious half over. Here's the fun one.
>
> That sound was not made by a bird. There's no crow. That's a computer, making
> up a crow noise that has never existed.

`[VISUAL]` Simple animation: audio → coloured symbols → symbols → audio.

> The trick is that you can chop sound into little symbols — like letters, but
> for audio. And once sound is a sequence of symbols, you can do the exact same
> thing ChatGPT does with words: guess what comes next. Then the next. Then the
> next.
>
> Same idea. Just very, very small — this thing is roughly a ten-thousandth the
> size of a real language model, and it trained on the graphics card already in
> my desktop in about an hour.

> And here's my favourite part: **it never saw a single human label.** Nobody
> told it what an alarm call is. It just listened to a lot of crows and worked
> out what crows sound like.
>
> I'd nearly abandoned this because I only had a few dozen labelled calls. Then
> I realised — a model that *copies* crows doesn't need labels. It just needs
> crows. And I had a hard drive full of those.
>
> When I actually measured it, my archive turned out to be about **sixty percent
> crow** by runtime. Everyone I asked, including me, had guessed maybe fifteen.
> The problem I'd been stuck on for a week wasn't real.

### The important bit: how do you know if it worked?

`[VISUAL]` Open the listening test page. Full screen.

> Now — how do you know if a fake crow is any good?
>
> Not by listening to it yourself and going "yeah, sounds crow-ish." That's
> worthless. You *know which one you made.* You'll hear what you want to hear.
>
> So I built this.

`[VISUAL]` Click through several trials on camera. Commit, then reveal.

> Half of these clips are real recordings the model has never heard. Half are
> invented. You have to commit to an answer before it tells you. It's the same
> way they test whether people can actually taste the difference between wines.
>
> And critically — **you're trying to fail.** If I can reliably spot the fakes,
> the model isn't good enough.

`[VISUAL]` Score card.

> I did sixty of these. And I could spot it most of the time — so, a loss.
>
> But it fooled me **ten times out of thirty.** And a few times I confidently
> called a *real crow* fake, which I enjoyed a lot less.

`[VISUAL]` Play three generated clips in order, oldest to newest.

> Here's the progression, in my own notes at the time:
>
> Early on: *"vaguely crow-like."*
> Then: *"still scratchy, but now it sounds like a robot crow."*
> And now: *"more like a cyborg — still a bit robotic, but still a crow."*
>
> Which I think is genuinely the correct scientific term.

---

## PART 5 — THE TIMES I WAS ABOUT TO BE WRONG (10:00)

`[VISUAL]` Slow down. Different music. This is the heart of the video.

> I want to spend two minutes on the part nobody puts in these videos.
>
> I keep a folder of little experiments. One question, one answer, written down
> — **including when the answer is boring.** There are twenty-five of them now.
>
> And going back through them, nearly every single one has a moment where the
> tidy version of the story would have been *completely wrong.*

**"My microphone is distorting, I need to turn it down."**
> It wasn't distorting. Two tiny bumps in an hour — I'd knocked the cable. Also
> that microphone has no volume control, so there was never a knob to turn. I
> withdrew that advice about forty minutes after giving it. To myself.

**"The lawnmower ruined these recordings."**
> Four recordings, lawnmowers going, everything came back "alarm call." Obvious,
> right? Then I measured a *good* recording and found it's just as full of
> low rumble. A city is mostly rumble whether or not anyone's mowing.
>
> The mower was innocent. But hunting for it turned up something much worse:
> when the model is *least* sure it's even hearing a crow, it gets *more*
> confident about what kind of call it is. Which is exactly backwards. That
> number isn't confidence. It's something else wearing confidence's clothes, and
> I'd been reading it wrong.

**"The model is plagiarising."**
> I found my fake crows were reusing chunks of real recordings way more often
> than they should. Copying, basically. I wrote it up. It was the most damning
> thing in the project.
>
> Then I remembered there's a dial that controls how *adventurous* the model
> is — and mine was set to a value I'd typed once and never thought about. If it
> were really memorising, turning that dial wouldn't help; memorising is baked
> in. If it were just playing it safe, it'd vanish.
>
> It vanished. Completely. It wasn't copying, it was being timid.
>
> And my to-do list said to fix it by making the model *more* cautious — which
> was the exact opposite of right.

**"They sounded angrier at the stranger."**
> A stranger walked past the birds and they went off. To me, it sounded
> different from how they sound at me. And when I measured it — it *was*
> different! Longer calls, more of them.
>
> Then I checked whether the effect survived if I just made the recording a bit
> noisier. Half of it evaporated.
>
> And the real problem: I have exactly **one** recording of a stranger. So
> "stranger" and "that one afternoon" are, mathematically, the same thing. I
> can't tell them apart. Not disproven — **not yet answerable.**

**"I can tell the five crows apart by voice."**
> This was the dream. Caption *which bird* said what.
>
> So I tested it on a recording with five crows in it — and got a nice, clean
> result. Then I ran the control: the same test on a recording of **one** crow.
>
> Identical result. Exactly as much structure. It wasn't finding birds at all.
> It was mostly measuring **how far away they were.** I hadn't built a voice
> recogniser. I'd built a very elaborate tape measure.

**And then, three days ago, the best one.**

`[VISUAL]` Stop. Quiet.

> I finally sat down and tuned the fake-crow model properly. Ran the whole thing
> overnight, several versions, changing one thing at a time.
>
> It worked. Clean, obvious improvement. Best score the project has ever
> produced. I wrote in my notes that the next step was obviously to build a
> bigger model.
>
> Then I did the blind listening test on it.

`[VISUAL]` Two results, side by side. Just the two "fooled me" counts.

> And I could spot the fakes *more* easily than before. The old model fooled me
> ten times out of thirty. The new, better, definitively-improved model fooled me
> **four.**
>
> And before I'd seen any of the results, the note I wrote was: *"I feel like
> there was a minor quality degradation."*
>
> Now — sixty clips can't *prove* it got worse, and I'm not claiming that. What
> I'm claiming is that a big, clean, repeatable improvement in the score bought
> **nothing you can actually hear.**
>
> I deleted the "build a bigger model" plan an hour after writing it.

`[TEXT]` **Trust your ears over the scoreboard.**

> Which is, I think, the most useful thing in this entire video. The number you
> optimise is never the thing you actually want. It's a *stand-in* for the thing
> you want. And every so often you have to go and check that it still is.

---

## PART 6 — WHAT'S NEXT (12:00)

`[VISUAL]` Outside. Golden hour. Crows.

> So what's left?
>
> The surprising answer is: **not more software.** The classifier works. The app
> works. The server works. The fake-crow generator works, sort of, in a cyborg
> way.
>
> What's missing is *data*, and there's no clever shortcut for that.

`[VISUAL]` Three cards.

> **One: labelling.** That means me, with headphones, doing the same tedious job
> that crow-tools person did, for months. There's no computer you can rent that
> does that for you.
>
> **Two: being there when things happen.** Which is the dog problem. The plan is
> a camera and a microphone on the roof, running all the time, so I stop needing
> to be standing there. Though — a roof camera sees the *reaction*, not the
> *cause*. The dog is down at street level, out of frame. So I'll need both.
>
> **Three: which bird.** I still want to caption *who* said what. Audio alone
> can't do it — that's the tape-measure experiment, that door is closed. So now
> the app just asks me to note down who I *saw* calling, while I'm standing
> there. I can't identify a bird listening back later. I can identify one in
> front of me.

`[VISUAL]` The generator. Then a speaker outdoors. Then a warning card.

> And then there's the thing I'm most excited about and most nervous about.
>
> Remember the stranger problem — I only get one shot, whenever a stranger
> happens to wander past? You can't do science like that. You need to be able to
> repeat it.
>
> The way out is **playing sounds back to them.** That's how the real research in
> this field works. There's brilliant work on Japanese tits where researchers
> spliced calls together into orders that *never occur in nature* and showed the
> birds respond differently — and that finding only exists because the
> experimenter got to *choose the order*.
>
> Which is where the fake-crow generator stops being a toy. Its most valuable
> use isn't proving a computer can caw. It's **building sounds that no bird ever
> made**, so I can change one thing at a time and hold everything else still.

`[VISUAL]` Hard stop.

> **And I haven't done any of it, because there's a line to think about first.**
>
> Recording is passive. Playing sounds *at* wild animals is not. If you play an
> alarm call, real birds stop eating and go looking for a threat that isn't
> there. And a family you're planning to study for years is exactly the family
> you shouldn't be lying to for fun.
>
> So the rules get decided *before* the first playback, not after. And here's
> the thing that makes me trust myself on it: a family that stops believing you
> is a *ruined experiment* as well as a wronged one. Being careful and being
> rigorous point the same direction, which is a nice place to be.
>
> There's one clean exception I like a lot. A fake **food call**, played while
> I'm actually putting food down, isn't a lie at all. That's probably where this
> starts.

`[VISUAL]` Two arrows forming a circle.

> And the long game, which is a long way off.
>
> I've got something that turns a crow sound into a category. And something that
> turns a category back into a crow sound. Point them at each other and you've
> technically got a round trip.
>
> But that's a four-word phrasebook, and the plumbing was never the hard part.
> The real version isn't asking for a *call type* — it's asking for a
> *situation*. Say "food here," and get back a call that matches what my crows
> actually sound like when there's food.
>
> And that has a cost that never goes away. Downloaded audio is free and
> infinite, and none of it comes with a witness. Every single situation has to be
> paid for by somebody standing outside, watching, one afternoon at a time.
>
> Right now I've got six recordings of food arriving. And they don't agree with
> each other — three different call types across six moments.
>
> Which isn't a failure. That's the data telling me exactly what to go get.

---

## OUTRO (14:00)

`[VISUAL]` Edgar. Then the repo.

> All of this is free and open. The code, the plans, and all twenty-five
> experiments — including the ones that found nothing, and the ones where I take
> back what I said. Links below.
>
> Two things I'd genuinely like.
>
> **If you have crows that know you** — if you're one of those people with a
> corvid family that recognises your face, and you own a phone — that's the one
> thing I can't do myself. I have one family, one backyard, one city. Every
> interesting question about whether crows have regional accents needs more
> families than one person can watch. I'll say clearly when I'm ready for that,
> rather than pretending I already am.
>
> **And if I've got something wrong, please tell me.** Especially if you actually
> study birds, because you have every right to be suspicious of a software guy
> turning up with a neural network and opinions about what crows mean.

`[VISUAL]` Final card.

> So — I have not decoded crow language.
>
> What I've got is software that can tell some crow calls apart, a phone that
> records them properly, eighteen real recordings, one dog, and a folder full of
> the times I nearly fooled myself.
>
> That's a start. It isn't a discovery. And I think the difference between those
> two things is most of what doing this properly actually is.
>
> Thanks for watching. Go say hi to your crows — they remember faces, and
> apparently they hold a grudge for years, so it's worth staying on the good
> list.

---

## PRODUCTION NOTES

### What changed from draft 1

Draft 1 was written at the repo's altitude: AUC tables, codebooks, nats,
silhouette scores. Correct and unwatchable. This draft keeps the same spine and
throws out nearly every figure.

The four lessons are the actual teaching payload, and they're all transferable
outside birds — that's what makes it educational rather than a project tour:

1. A specialist model beats a generalist.
2. Better labels beat better AI.
3. Don't trust a device's own paperwork.
4. You can't schedule a dog. *(Rare events are a calendar problem.)*
5. Trust your ears over the scoreboard. *(Your metric is a stand-in. Check it.)*

Numbers that survived, and why — each is a *picture*, not evidence: **eighteen**
real recordings, **one** dog, **ten out of thirty**, **sixty percent** of the
archive, **several thousand seconds** hand-labelled. Everything else went to the
description.

### Demos to record

| # | What | Where |
|---|---|---|
| 1 | Analyzer labelling a recording | `make analyzer` on `data/audio/interesting-example.mp3` — show the coloured blocks, not the terminal |
| 2 | The phone app | Screen record on the Pixel 8: record → waveform → label → sync |
| 3 | The dashboard | `make field`, drag a file on, watch calls appear |
| 4 | The blind listening test | `crowgpt/results/demo-model-d384-6k-american-crow.html` — record a genuinely unrehearsed sitting |

Draft 1 also used `compare.html` and `demo-calltype.html`. Both cut — they answer
questions this version never raises.

### Re-check before shooting

The corpus moves. Re-count kept captures and context tags on the day. **If
`dog_visible` has gone above one, the Part 3 punchline breaks** — which would be
excellent news and an easy rewrite.

### Before publishing

- [ ] **Strip GPS.** Recordings carry exact coordinates. Nothing showing a map, a
      recording's details, or raw server output goes on screen unchecked. That's a
      home address.
- [ ] Blur the server password anywhere the settings screen is visible.
- [ ] Archive clips used as examples: run the list past Ben before the edit
      locks — which recordings may appear is his call.
- [ ] Credit crow-tools **on screen**, not just in the description.
- [ ] The title must not contain the word "decoded."

### Still blocking the ask

From [outreach.md](outreach.md): the "send me your recordings" ask in the outro
isn't honest yet. There's no encryption and a single shared password, which is
fine on my home network and not fine for strangers. Either that ships first, or
the outro softens to "watch the repo." A funding link should exist by then too.

### Tone

Every story in Part 5 is a story about being wrong. Play them straight — not
sheepish, not smug. They're the most credible thing in the video, and hamming
them up turns them into a bit.
