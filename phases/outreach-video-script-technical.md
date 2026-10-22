# Video script (technical cut) — "I spent two weeks trying to understand my crows"

Written 2026-08-01. **The deep cut**, for people who want the numbers. The
audience is r/MachineLearning, Hacker News, bioacoustics people, and anyone who
watched the [general version](outreach-video-script.md) and wanted to know what
was actually measured.

Target **20–22 minutes**. The two scripts share a spine and almost nothing else:

| | [general cut](outreach-video-script.md) | this one |
|---|---|---|
| length | ~13 min | ~22 min |
| audience | r/crows, people who like birds | HN, ML, bioacoustics |
| figures | five, all of them pictures | every one that carries weight |
| method | analogies — "letters, but for audio" | EnCodec, 8 codebooks, 6 kbps |
| the wins | five portable lessons | eleven retractions with the evidence |

Publish the general one first. This is the follow-up for the comment section
that asks how it actually works — that audience arrives *after* the first video
lands, and they arrive already knowing whether they care.

Every number here was read out of the repo or the live database on the day of
writing. Where a number is fragile — one recording, six spans, thirty trials —
the script says so out loud, because the [one rule](outreach.md#one-rule-dont-overclaim)
is that the honest version travels further with the people whose data we want.
This audience in particular will go and check.

**Working title:** *Can AI Understand Crows? I Spent Two Weeks Finding Out*
**Backup:** *I Built an AI to Talk to the Crows in My Backyard (It Half Worked)*

Format notes: `[VISUAL]` is what's on screen, `>` is spoken narration,
`[ON-SCREEN]` is a text overlay. Demos are real commands against this repo.

---

## COLD OPEN — 0:00

`[VISUAL]` Black. Two waveforms fade in, side by side. Play caw A. Play caw B.

> Listen to these two sounds.

`[VISUAL]` Play each again, isolated, with the spectrogram scrolling.

> Both of those are American Crows. Same species, same bird family, recorded
> forty feet from my back door. One of them is an alarm call. One of them isn't.
>
> If you can't tell — that's fine. Neither could I, for the first week.

`[VISUAL]` Terminal. Run the analyzer live on `data/audio/interesting-example.mp3`.
Real output scrolls:

```
loading BirdNET + call-type heads…
ready — heads: American Crow, Carrion Crow, Common Raven, Hooded Crow, Rook

 0.0– 12.0s  American Crow   flight call   crow 0.989
12.0– 15.0s  Hooded Crow     call          crow 0.318
18.0– 24.0s  American Crow   flight call   crow 0.995
36.0– 39.0s  American Crow   alarm call    crow 0.937
45.0– 51.0s  American Crow   call          crow 0.989
60.0– 63.0s  American Crow   alarm call    crow 0.967
66.0– 69.0s  American Crow   alarm call    crow 0.620
69.0– 72.0s  American Crow   alarm call    crow 0.919
84.0– 90.0s  American Crow   call          crow 0.983
```

> That's a model, running on my laptop, finding every crow in ninety seconds of
> audio, naming the species, and saying what *kind* of call each one was.

`[VISUAL]` Beat. Then cut to a photo of Edgar (`images/edgar-full-image.jpg`).

> This is Edgar. He's a yearling crow who helps guard his parents' nest, and
> he's one of five birds this whole project exists for.
>
> Now — the honest part, up front, so nobody has to wait for it. **I have not
> decoded crow language.** Nobody has. What I've built tells you what a call
> *sounds like*, not what it *means*. Those are two completely different
> problems, and today only one of them works.
>
> This video is about the one that works, the one that doesn't, and roughly
> eleven times I nearly believed something that turned out to be false.

`[VISUAL]` Title card.

`[ON-SCREEN]` *CrowGPT — an open-source attempt to understand crows*

---

## ACT 1 — THE TWO PROBLEMS (1:15)

`[VISUAL]` Whiteboard animation. One box splits into two.

> Here's the thing that took me embarrassingly long to realise. "What is the
> crow saying" is not one question. It's two, and they need completely
> different machinery.

`[ON-SCREEN]`
```
1. WHAT ARE THE CALL TYPES?     → acoustics. A classification problem.
2. WHAT DOES EACH TYPE MEAN?    → semantics. Needs a witness.
```

> **Problem one is acoustics.** Are crow calls even separable into categories a
> machine can tell apart? That's a normal machine-learning problem. You need
> audio and labels.
>
> **Problem two is semantics.** Does "this call" mean "I see a dog"? You cannot
> get that from audio alone, ever, no matter how much of it you have. You need
> the call *paired with what was actually happening* — and that means somebody
> standing there watching.
>
> Keeping those two apart is the main design decision in this entire project,
> and I'll come back to why near the end.

`[VISUAL]` The five crows, as a family tree card. Photos where they exist.

> The birds are the Poe family. Thrasher and Ripjaw are the parents. Killer and
> Shredder are the fledglings. Edgar is the yearling who sticks around and
> helps. Yes, I named them. Yes, I regret the naming scheme. No, I'm not
> changing it now.
>
> Shredder calls back when I say "bye buddies." That's not a data point. That's
> just why I started.

`[VISUAL]` Scope card.

> One scope note, because it matters for everything after this. I'm only working
> on **loud, public calls.** Crows also do this quiet muttering thing —
> "subsong" — that probably carries far more information. It also needs a
> microphone about a foot away and drowns in traffic noise from any further. So
> it's out. Loud calls are stereotyped and repeated, which is exactly what a
> model with very few labels needs.

---

## ACT 2 — TEACHING A MACHINE TO HEAR A CROW (3:00)

### The problem with audio

`[VISUAL]` A raw waveform, then the number of samples counting up.

> Three seconds of audio at 48 kilohertz is about a hundred and forty thousand
> numbers. You cannot hand that to a classifier. So the first job is turning
> sound into a *fingerprint* — a fixed-length list of numbers where two calls
> that sound similar end up near each other.
>
> That's called an embedding, and picking the right one was Phase 3.

### DEMO 1 — the bake-off

`[VISUAL]` Three-column table filling in as each is described. Show the actual
report at `pipelines/representation/results/report.md`.

> I tried three. Here's what happened, on 117 hand-checked crow clips.

**Attempt 1 — classical audio features (MFCCs).** The textbook approach.

`[VISUAL]` The t-SNE plot. It's a blob.

> Silhouette score: minus 0.06. Cluster agreement with the true labels: 0.008.
> For scale, zero is "you learned nothing." This is a picture of nothing.

**Attempt 2 — a general-purpose audio transformer (AST).**

> Trained on AudioSet — millions of general sounds. Better. Macro-F1 went from
> 0.36 to 0.48. Still not usable.

**Attempt 3 — BirdNET.**

> BirdNET is Cornell's model, trained on *millions of bird recordings.* Its
> internal representation already separates bird sounds from each other, because
> that is the only thing it has ever been asked to do.

`[VISUAL]` The AUC table, animated in.

| Call type | Classical | AST | **BirdNET** |
|---|---|---|---|
| flight call | 0.77 | 0.74 | **0.89** |
| call | 0.62 | 0.55 | **0.71** |
| alarm call | 0.77 | 0.67 | 0.67 |
| song | 0.49 | 0.61 | 0.47 |

> And here's the moment the project actually got interesting — because look at
> that table again. **BirdNET didn't win everywhere.** Flight call jumped. But
> alarm call got *worse*, and song stayed at chance.
>
> The naive read is "BirdNET is unreliable." The correct read is that these are
> two different failures wearing the same costume.

`[ON-SCREEN]`
```
REPRESENTATION-LIMITED → the model can't see the difference
LABEL-LIMITED          → the model can see it fine. Your labels are garbage.
```

> Flight call was representation-limited. A better embedding fixed it.
>
> Alarm and song were **label-limited.** My labels came from a public archive — a
> community bird-recording archive where people type whatever they want into a
> free-text "type" field. If half your "alarm calls" aren't alarm calls, no
> architecture on earth saves you.
>
> Which means the fix isn't a better model. The fix is better labels. And I
> could test that, because somebody had already done the hardest possible
> version of the work.

### The part that isn't mine

`[VISUAL]` The crow-tools GitHub page. Hold on it.

> This is **crow-tools**, by OpenShot Studios. MIT licensed. It contains
> **3,162 hand-reviewed segments across 1,549 recordings.**
>
> That is a human being sitting down and listening to several thousand seconds of
> crow, one second at a time, and writing down what each one was. The project is
> no longer maintained. I've vendored the labels into my repo so they outlive the
> fork, with attribution, under its own licence.
>
> Same pipeline. Same features. Same code. Only the labels changed.

`[VISUAL]` Side-by-side of the two `metrics.json` files, real, from the repo.

| Class | archive weak labels | crow-tools clean labels |
|---|:---:|:---:|
| alarm call | 0.724 | **0.939** |
| song | 0.649 | **0.904** |
| call | 0.699 | **0.950** |
| flight call | 0.913 | **0.975** |
| begging | — | **0.914** |

> Alarm call: 0.72 to 0.94. Song: 0.65 to 0.90. Every class now above 0.90.
>
> That is the difference between a classifier that doesn't work and one that
> does, and **none of it was my labour.** I want to be really clear about that,
> because the single biggest result in this project came from somebody else
> doing thousands of seconds of listening for free and putting it on GitHub.

`[VISUAL]` A tangent card: the head design.

> Two small engineering notes, because they're both counterintuitive.
>
> First, on top of BirdNET's fingerprint I use **logistic regression.** Not a
> neural network. I tried a neural network — it got macro-F1 0.35, and the
> boring linear model got 0.48. At a few hundred examples per class, the simple
> thing wins, and I'd rather ship the simple thing.
>
> Second, there's **one model per species.** If the analyzer detects a Rook and
> I don't have a Rook call-type head, it reports "Rook" and stops. It does *not*
> hand the audio to the American Crow model. A Rook's call type guessed by a
> crow's classifier is a fabrication, and downstream nothing would tell it apart
> from a real answer.

`[VISUAL]` Back to the cold-open analyzer output, freeze on the 66-second row.

> You can actually see this in the demo from the top of the video. At 66 seconds
> it flags American Crow, but also Carrion Crow and Hooded Crow as *candidates* —
> lower confidence, marked separately, not silently averaged into one answer.

---

## ACT 3 — THE FLEET (8:00)

`[VISUAL]` Phone in hand, walking outside. Real field footage.

> Okay. The classifier works. Which means the bottleneck moved, and it moved
> somewhere much less fun: **I now need recordings of my own crows, with notes
> about what was happening.** Archive audio can't answer problem two, because a
> archive clip doesn't come with a witness.
>
> So I built a small fleet.

### DEMO 2 — the app

`[VISUAL]` Screen recording: open app, hit record, waveform moves, stop, capture
appears in the list.

> This is an Android app. It records, it tags GPS, it lets me label calls by
> hand, and it syncs — **only when I press the button.**

`[VISUAL]` Zoom on the audio settings.

> One detail I care about more than it deserves: it records **unprocessed 48 kHz
> audio.** Your phone normally runs automatic gain control and noise suppression
> on every recording, tuned for human speech. That machinery looks at a faint
> structured bird call and decides it's noise, and quietly mangles it.
>
> So the app asks Android for the `UNPROCESSED` microphone source. And here's
> the fun bit — my Pixels **decline to certify** that they support unprocessed
> audio, and then hand it over anyway when you ask. So the code doesn't check the
> capability flag. It just tries to open the source, and then reads back what it
> actually got, per recording. Every capture records which microphone path it
> really used, as a measurement, not an assumption.

`[VISUAL]` Sync animation: phone → server → worker → back.

> Sync is **push-only.** The phone is the source of truth; the server never
> writes back over a recording. That rule exists because the failure it prevents
> — a stale server copy overwriting a real field recording — is unrecoverable,
> and the thing it costs is mildly annoying.
>
> There's exactly one exception: a Restore button that pulls down captures the
> phone doesn't have and never touches one it does. Capture 69 survived a
> reinstall only because of that.

### DEMO 3 — the dashboard

`[VISUAL]` Browser. `make field`. Open `http://127.0.0.1:5100`. Drag an audio
file onto the dropzone. Watch it upload, get analyzed, and calls appear on a
waveform.

> The server takes the upload, a separate worker picks it up, runs BirdNET, and
> writes the results back. The server and the worker share one SQLite file and
> nothing else — no HTTP between them. That means inference can take as long as
> it takes without the API ever blocking, and the worker can run on a different
> machine, or not at all, and nothing else notices.

`[VISUAL]` The capture detail panel — waveform, detected calls, human labels.

> And then the actual work. Three kinds of ground truth, kept deliberately
> separate:

`[ON-SCREEN]`
```
LABELS       what the bird said        → the only thing that trains a model
CONTEXT      what a human saw          → attached to the CALL, not the recording
OBSERVATIONS free text, written after  → where new tags come from
```

> That middle one has a subtlety I got wrong first. Context tags attach to the
> **individual call**, not to the whole recording. If you tag the whole file,
> then a clip where a dog walks past and the crow *later* sings would report
> that crows sing at dogs. Every situation gets credited to every call. The
> matrix would fill up with garbage that looks exactly like a finding.

`[VISUAL]` The "by ear" button.

> There's also a button to mark a call **by ear**, with no detection behind it.
> This matters much more than it sounds. BirdNET scores a begging fledgling at
> **0.06.** If I only ever confirmed the model's detections, I could only ever
> collect data on the calls it already finds — and the classes it's worst at
> could never, ever improve. The model's blind spots would be permanent.

### The honest state of the corpus

`[VISUAL]` The dashboard's own stat tiles, live.

> Now the part where I show you the numbers and they're small.

`[ON-SCREEN]` (live, 2026-08-01)
```
114  captures
 18  ★ real field recordings   ← the rest is seeded archive audio + test uploads
 52  human labels, across 11 captures
141  context events
319  model detections
  2  contributors (me, and me again)
```

> A hundred and fourteen captures. **Eighteen** of them are real recordings of
> real crows I was standing next to. The rest is seeded archive audio and the
> same test file uploaded several times, which is how you test a pipeline.
>
> So any count over all captures is a fact about **my software**, not about
> crows. The dashboard labels which one it's showing, because I kept confusing
> myself.

`[VISUAL]` The calls × context matrix. Live, real.

> And here's the semantics view. Every human-labelled call, against what I saw
> while it happened.

| | crows_still | human_approaching | human_gives_food | dog_visible |
|---|:---:|:---:|:---:|:---:|
| alarm call | 19 | 9 | 2 | — |
| begging | 4 | 4 | 2 | — |
| call | — | 2 | — | — |

`[VISUAL]` Slow zoom on the `dog_visible` column. It contains the number 1.

> The original plan for this entire project — Phase Zero, written before I'd
> built anything — was: *does a distinct acoustic cluster line up with dog
> events?*
>
> After two weeks, my corpus contains **one** dog event.

`[VISUAL]` Beat. Let it land.

> This is the whole lesson of the field-collection half. There's a line in my
> notes I keep coming back to: **you can't schedule a dog.** Rare-context calls
> are not an hours problem, where you go out and grind for a weekend. They're a
> *calendar* problem. You need weeks of continuous recording, because you cannot
> make a hawk fly over on a Tuesday.

---

## ACT 4 — TEACHING A MACHINE TO CAW (12:30)

`[VISUAL]` Hard tonal shift. Synth. Waveform of a generated caw.

> Okay, that's the serious half. Here's the half that's just fun.

### Why it wasn't dead

> At the time I had **thirty-five** human labels. Total. So generating crow calls
> was obviously impossible, and I nearly filed it away.
>
> Then I noticed the premise was wrong. A generative model doesn't need labels.
> **It needs audio.** And I already had a hard drive full of it.

`[VISUAL]` The scan running, numbers filling in.

> So I measured. 2,675 files, 40.8 hours of archive audio. Everyone I asked
> guessed maybe ten to twenty percent of it was actually crow, and the rest
> ambience.
>
> It's **61.6 percent.** Twenty-four and a half hours of actual corvid, cutting
> into roughly **sixty-five thousand** discrete call units, median length 0.376
> seconds.
>
> The blocker was imaginary. That's a recurring theme.

### How it works

`[VISUAL]` Animated pipeline: audio → EnCodec → tokens → transformer → tokens →
audio.

> The trick is that you can turn audio into **tokens** — a fixed vocabulary of
> discrete symbols — using a neural codec. I use Meta's EnCodec at 24 kHz,
> 6 kbps, 8 codebooks. Once audio is a sequence of symbols, you can do the exact
> thing GPT does to text: predict the next one.
>
> The model is a causal transformer, 6 layers, 4 heads, **18 million
> parameters.** For scale, that is around one ten-thousandth of a modern language
> model. It trained on the graphics card that was already in my desktop, in about
> an hour and a half.
>
> It's small on purpose. I have millions of tokens but only about 2,700
> independent recordings, and a bigger model just memorises them.

`[VISUAL]` Highlight the "bout" concept.

> One design choice worth a second: the unit is a **bout**, not a single call.
> Bursts within 1.5 seconds get merged, capped at three. Because if you train on
> isolated caws, you then have to hand-invent the gaps between them at exactly
> the moment somebody is judging whether it sounds real. Rhythm *is* the thing.
> So learn it.

### DEMO 4 — the blinded listening test

`[VISUAL]` Open `crowgpt/results/demo-model-d384-6k-american-crow.html` in a
browser. Full screen. Play a clip.

> Now — how do you know if it worked?
>
> Not by listening to it yourself and going "yeah, sounds crow-ish." That's
> worthless, because you know which one you made.

`[VISUAL]` Click through several trials on camera, committing to an answer each
time, revealing.

> So this is a **blinded forced-choice test.** Half these clips are real
> archive recordings the model has never heard. Half it invented. You have to
> commit before it tells you. It records your answer, your decision time, how
> many times you replayed it, and it stamps the whole sitting with a
> **fingerprint of the model's actual weights**, so two checkpoints can never get
> averaged together by accident.
>
> Chance is fifty percent. You're trying to *fail* this test.

`[VISUAL]` The score card at the end.

> Sixty trials. I got **75 percent.** Which is a loss — the model didn't fool me.
>
> But it fooled me **10 times out of 30.** And 5 times out of 30 I called a real
> crow fake. Errors in *both* directions, which is not what a purely robotic
> output produces.

`[VISUAL]` Play three generated clips in sequence, captioned with the training
checkpoint.

> Here's the progression, in my own words at the time:
>
> Six thousand steps: *"vaguely crow like."*
> Twenty-four thousand: *"still scratchy but now it sounds like a robo crow."*
> Forty thousand: *"American Crow is getting really good... more like a cyborg,
> so still a little robotic but still a crow."*

### DEMO 5 — is it the codec or the model?

`[VISUAL]` Open `crowgpt/results/compare.html`. Play all three arms on one
species.

> And when it sounds bad, whose fault is it? Because there are two suspects: the
> codec might be throwing the caw away before training even starts, or the model
> might never have learned it.
>
> So this page plays the same window three ways. Real. Real *through the codec,
> touching no model.* And generated.

`[VISUAL]` Play them.

> The codec arm scores 0.79 to 0.99 — on American Crow it actually beats the
> original. The generated arm sits between 0.0 and 0.69.
>
> **It's the model.** The tokenizer is fine.

### Why it sounds like a cyborg — mechanically

`[VISUAL]` Bar chart, 8 bars, descending, last three below zero.

> This is my favourite result in the whole project, because it explains the
> sound.
>
> Those 8 codebooks are a stack: the first carries the coarse shape, each one
> after adds finer detail. I measured how much the model actually learned about
> each, in bits over the codec's own baseline:

`[ON-SCREEN]`
```
1.96  1.32  1.01  0.54  0.21  -0.03  -0.24  -0.41
```

> **Three of the eight are generated at essentially chance.** The model has a
> decent coarse signal with structured-looking noise painted over it.
>
> And when I ran the listening test, before seeing any of these numbers, I wrote:
> *"some sound kind of xylophone-esque where it's choppy and changes tone
> rapidly."*
>
> Three codebooks of noise over a coarse signal is *exactly* what that sounds
> like. A bits-per-stage table and a guy with headphones arriving at the same
> place independently is the strongest evidence this project has.

### DEMO 6 — asking for a call type

`[VISUAL]` `crowgpt/results/demo-calltype.html`. Play a requested alarm call
next to a real one.

> Last one. You can *ask* it for a call type — the type is just a prefix token,
> like a prompt.
>
> It works. 41.6 percent match against 25.5 percent chance. But look at the
> per-class breakdown, because it's the most beautifully boring result I've ever
> generated:

| Requested | Training examples | It complied |
|---|---:|---:|
| alarm call | 26,876 | **92.9%** |
| begging | 2,349 | 50.0% |
| song | 1,113 | 16.4% |
| call | 272 | **3.8%** |

> Perfectly monotonic across four orders of magnitude. There's no mystery here.
> The method works fine. The constraint is **data per class**, and the rule of
> thumb that fell out is: budget a couple of thousand examples per value before
> you expect any control at all.

---

## ACT 5 — THE ELEVEN TIMES I WAS ABOUT TO BE WRONG (17:00)

`[VISUAL]` Fast montage. Each beat gets ~15 seconds, a card, and a punchline.
Keep the pace brutal.

> I want to spend two minutes on the part nobody puts in these videos.
>
> I keep a folder called `experiments`. One question, one folder, one answer
> written down — **including when the answer is boring.** There are 25 of them
> now. And going back through them, almost every single one has a moment where
> the tidy version of the write-up would have been *wrong*.

**"The microphone is clipping, turn the gain down."**
> 195 clipped samples. Turned out to be two bumps, 3 milliseconds and 21
> milliseconds — a hand, or a cable. That's not a hot microphone, that's a
> well-set one meeting two transients. Also the mic **has no gain control**, so
> there was never a dial to turn. Recommendation withdrawn within the hour.

**"The furry windshield costs 7 dB of signal-to-noise."**
> It measurably did. And BirdNET's confidence went *up*. A measure and its
> consequence can't move in opposite directions if the measure is describing
> what happened. The two recordings were different content — one was a *begging
> fledgling*, so the "silence" the ratio divides by was different silence.
> The tidy write-up would have taken the windshield back off.

**"An hour of listening killed the battery and the mic got reaped."**
> It would have said that. My monitoring harness checked for `standby: 0` and
> this phone writes `Standby: no`. It would have logged "microphone CLOSED" for
> all 112 samples — the exact inverse of the truth. Caught by reading the raw
> dumps by hand before the run. The real answer: 3.7% per hour, and the battery
> got *cooler*.

**"The lawn mower ruined these recordings."**
> The rumble looked damning until I measured a *good* recording, which is 78.8
> percent low-frequency energy. A city is mostly rumble whether or not anyone is
> mowing. The mower was innocent — but the investigation found something worse:
> 32 percent of call-type predictions come out at probability **exactly 1.000**,
> and they skew toward the audio BirdNET was *least* sure was a crow. That number
> isn't confidence. It's closer to a distance-from-training-set measure.

**"A 2 kilohertz lowpass filter is a better tokenizer than a neural codec."**
> I put a deliberately-ruined arm in a codec experiment specifically to prove my
> metrics could fail. **The ruined arm won.** If I'd run that experiment with the
> obvious cheap design — one metric — that's the conclusion I'd have published.

**"The model is plagiarising its training data."**
> Generated audio shared an exact fingerprint with the training set 37.5 percent
> of the time, against 4.3 percent for real held-out audio. Eight and a half
> times. Damning. Wrote it up. Then: memorisation lives in the *weights* and
> doesn't care about sampling temperature. Mode-seeking lives in the *sampling*
> and melts. Turned the temperature up to 1.15 and the overlap became **0.043 —
> the real base rate, to three decimals.** It was a default I'd typed while
> writing the file and never measured. My to-do list said to fix it by sampling
> *colder*, which was precisely backwards.

**"The crows sounded angrier at the stranger."**
> They did, to me. Their calls were nearly twice as long at two and a half times
> the rate. Then I ran a control — added 9 dB of noise — and it destroyed 49
> percent of the effect. And the fatal problem: my "stranger" corpus is **one
> recording.** "Stranger" and "that particular walk on that particular day" are
> currently the same variable. Not disproven. **Not yet testable.**

**"I can tell the five crows apart from audio."**
> A recording with five crows in it produces cluster scores of 0.195 and 0.131.
> A recording of *one* crow produces 0.196 and 0.100. Identical. What the
> clusters actually track is **loudness** — 81 percent of the structure in one
> capture. I hadn't built a bird identifier. I'd built a rangefinder.

**"Common Raven is the worst species."**
> Raw score said 0.258, dead last, flatly contradicting what I heard. But the
> *codec ceiling* differs by species — real raven through the codec only reaches
> 0.347, half what crow gets. Normalised against what's actually achievable,
> Raven goes from last to third. And American Crow turns out to be at **99
> percent of its ceiling**, meaning more data and more compute literally cannot
> move it.

**"WAV versus FLAC, obviously a wash."**
> 77 of 77 files bit-identical, and field recordings compress to **22.4 percent**
> — nearly twice the published figure, because crow audio is *quiet*: a bird ten
> metres up peaks at −30 dBFS with long silences, and quiet audio carries less
> entropy. Also decodes faster than WAV. 118 megabytes became 45. Per contributor
> per year: 2.4 gigabytes down to half a gig. I had a home NAS on the shopping
> list, budgeted at a one-terabyte threshold. That's now about **1,850
> contributor-years away.** One flag deleted a hardware project.

**And the one from three days ago.**

`[VISUAL]` Slow down. Change the music.

> I finally measured whether the generator was underfit, and immediately found
> that the number I'd been steering by for the whole project was broken — it
> compared one training minibatch *with dropout active* against a clean
> evaluation average. Two different measurements pretending to be a gap. Every
> capacity decision I'd made was made blind.
>
> Fixed it, ran a proper five-arm sweep. The model was unambiguously underfit.
> Removing dropout helped monotonically. And I found that a **batch size of 32
> had been silently running as 16 for the entire project**, clipped by a memory
> constant I never chose.
>
> Combined the two knobs that worked. Validation loss **4.538** — the best number
> this project has ever produced, 0.164 nats below the shipped model. Clean,
> monotonic, reproduced across five arms.
>
> Then I sat down and did the blinded listening test on it.

`[VISUAL]` The two score cards, side by side.

| | val loss | I identified it | it fooled me |
|---|---:|---:|---:|
| old model | 4.711 | 75.0% | 10 / 30 |
| **better model** | **4.538** | **88.3%** | **4 / 30** |

> The better model is the **more obvious** one. And before I saw a single number,
> the note I wrote was: *"I feel like there was a minor quality degradation."*
>
> Now — thirty pairs can't prove that. The honest statistics say the difference
> isn't significant. The claim is not "it got worse." The claim is that **0.164
> nats of improvement bought no audible improvement whatsoever, and what
> evidence exists points the wrong way.**
>
> An hour before that sitting I had written "more capacity is the evidenced next
> move." I deleted it. **The loss improved, the ear did not, and that is the
> finding.**

`[ON-SCREEN]` *Rank checkpoints by ear, not by validation loss.*

---

## ACT 6 — THE ROADMAP (20:00)

`[VISUAL]` Back outside. Golden hour. Crows.

> So. What's next.
>
> The surprising answer is: **not more machinery.** The classifier works. The
> app works. The server, the worker, the dashboard, the generator — they all
> work. Representation, training and assembly are all done.
>
> What's missing is **data**, and there's no clever way around that.

`[VISUAL]` Three numbered cards.

**1 — Labels.**
> Fifty-two human labels. It needs to be in the low thousands. That's me, with
> headphones, doing what the crow-tools person did, for months. There is no
> compute you can rent that substitutes for it.

**2 — Context, per call.**
> 141 events so far. One of them is a dog. This is the calendar problem, and the
> mitigation is a **roof station**: a weatherproof camera and an always-on
> microphone, running continuously, so I stop needing to be present when
> something interesting happens.
>
> One important design note there — the roof cam sees the *reaction*, not the
> *trigger*. The dog is at street level, off-frame. So the roof rig and the
> handheld kit answer different questions and I need both.

**3 — Individual birds.**
> I want to caption *which crow* said something. Audio alone can't do it at this
> range — that experiment is closed. So the app now records who I *saw* calling,
> live, in the moment. I can't name a bird listening back afterwards. I can name
> one while I'm standing there.

`[VISUAL]` The generator, then a speaker outdoors, then a warning card.

> And then there's the thing I'm most excited and most cautious about.
>
> Remember the stranger experiment — the one that failed because "stranger" and
> "that one walk" were the same variable? No amount of *recording* fixes that,
> because I don't control when a stranger shows up.
>
> The way out is **playback.** This is how the real work in this field gets done
> — Suzuki's research on Japanese tits found compositional syntax by
> recombining recorded call elements into orders that never occur in nature, and
> showing the birds respond differently. The finding only exists because the
> experimenter *chose the order.*
>
> Which is where the generator stops being a toy. Its highest-value use is not
> proving synthesis works. It's **manufacturing stimuli** — including
> recombinations and blends no bird ever produced — that can be varied along one
> axis while everything else is held still. Nothing else in this project can do
> that.

`[VISUAL]` Hard stop. Ethics card.

> **And I haven't done it, because there's a gate first.**
>
> Playback is an active intervention on wild animals, not passive recording.
> Alarm playback costs birds foraging time and can pull them toward a threat
> that isn't there. A neighbourhood family being studied for years is exactly
> the group you should not repeatedly alarm for a null result.
>
> So: the frequency ceiling and the no-alarm-near-fledglings rule get decided
> **before** the first playback, not after. A habituated family is a ruined study
> as well as a wronged one — and those two facts pointing the same direction is
> the only reason I trust myself here.
>
> There's one clean exception, and I like it a lot: a synthetic **food call**,
> played while food is actually being put down, isn't deception at all. That's
> probably where this starts.

`[VISUAL]` The two-halves diagram closing into a loop.

> The long game, and I'll be honest that it's a long way off. I have a model
> that goes **crow sound → category.** I have a model that goes **category →
> crow sound.** Joining those into a round trip is architecturally free — it
> already closes today, as a four-word phrasebook.
>
> But the plumbing was never the hard part. The target isn't conditioning on
> call *type* — it's conditioning on **context** directly. Say "food here" and
> get a call that matches the food-tagged calls in my field corpus.
>
> And here's the cost structure of that whole plan, which I want to be precise
> about. The call-type axis was free, because a classifier could auto-label
> 57,000 archive clips. **Context can never be free.** An archive recording
> carries no witnessed context and never will. Every single context value is
> paid for one field session at a time.
>
> Right now I have six food events. They're across five captures on five separate
> days, which is genuinely good experimental design. And they disagree — three
> different call types across six spans. Eighty-one seconds total.
>
> That's not a failure. That's the measurement telling me exactly what to go
> collect.

---

## OUTRO — THE ASK (22:00)

`[VISUAL]` Edgar. Then the GitHub repo.

> Everything here is open source. The code, the phase plans, the twenty-five
> experiments including all the ones that found nothing, and the write-ups where
> I retract my own conclusions. Link below.
>
> Two things I actually want.
>
> **One: if you have crows you know** — if you're one of those people with a
> corvid family that recognises you, and you've got a phone — that's the single
> thing this project can't generate for itself. I have one family, in one city,
> on one continent. Every dialect question, every "is this regional or is this
> just my birds" question, needs more families than one person can watch. The
> upload path is being built to be dead simple, and I'll say clearly when it's
> ready rather than pretending it already is.
>
> **Two: if I've got something wrong, tell me.** Especially if you're an
> ornithologist, because you have every right to be suspicious of a software
> person showing up with a neural network and opinions about corvid semantics.

`[VISUAL]` Final card.

> I'll finish where I started. I have not decoded crow language. What I have is
> a model that names call types better than chance, a phone that records them
> properly, a corpus of eighteen real recordings, one dog, and a folder of
> twenty-five times I nearly fooled myself.
>
> That's a start. It's not a finding.
>
> Thanks for watching. Go say hi to your crows — they remember faces, and
> apparently they hold grudges for years, so it's worth staying on the list.

`[ON-SCREEN]` github.com/benfaerber/crowgpt · *the honest version is in the READMEs*

---

## PRODUCTION NOTES

### Demos to record, in order

| # | What | How |
|---|---|---|
| 1 | Analyzer CLI | `make analyzer`, then `analyze(to_wav('data/audio/interesting-example.mp3'))`. Output in Act 2 is the real run. |
| 2 | Field app | Screen record: record → waveform → label → sync. Use the Pixel 8. |
| 3 | Dashboard | `make field`, drag a file onto the dropzone, watch the worker fill in the calls. |
| 4 | Listening test | `crowgpt/results/demo-model-d384-6k-american-crow.html` — record a genuinely blind sitting on camera. Do **not** rehearse it. |
| 5 | Codec vs model | `crowgpt/results/compare.html` |
| 6 | Call-type prompting | `crowgpt/results/demo-calltype.html` |

**Shoot 1–4 once and cut them both ways.** They are the same four demos the
[general cut](outreach-video-script.md) uses; only 5 and 6 are exclusive to this
script. The narration differs, the footage does not.

The one thing that cannot be shared is the **listening test sitting**. Both
scripts want a genuinely blind run, and once you have sat the test you are no
longer a naive listener — the clips stop being new. Record one unrehearsed
sitting, use that take in both, and do not re-shoot it for a better score.

### Numbers to re-verify on shoot day

The corpus moves. Re-run before recording Act 3:

```sql
SELECT COUNT(*) FROM captures;
SELECT COUNT(*) FROM captures WHERE keep=1;
SELECT COUNT(*) FROM labels;
SELECT COUNT(*) FROM context_events;
SELECT key, COUNT(*) FROM context_events GROUP BY key ORDER BY 2 DESC;
```

If `dog_visible` has climbed above 1, the Act 3 punchline needs rewriting — and
that would be excellent news.

### Things to check before publishing

- [ ] **Strip GPS.** Captures carry full-precision coordinates. Nothing showing
      a map, a capture detail panel, or a raw API response goes on screen
      without checking. Seven decimal places is a home address.
- [ ] **Blur the enrollment token** anywhere the Settings screen or
      `make -C fieldserver secrets` is visible.
- [ ] Archive clips used as audio examples: run the list past Ben before the
      edit locks — which recordings may appear is his call. Keep recordist
      attribution for every clip that does.
- [ ] Credit crow-tools on screen, not just in the description.
- [ ] The title must not contain the word "decoded".

### Prerequisites the video is blocked on

From [outreach.md](outreach.md) — these should be true before it drops:

- [ ] A dead-simple upload path for contributors. **Currently blocking**: there's
      no TLS and enrollment is one shared secret, which is fine on a home network
      and not fine for strangers. Either ship that or cut the Act 6 ask down to
      "watch this repo".
- [ ] A funding path (Ko-fi / Patreon).
- [ ] The write-up and code public, so it reads as a real open effort.

### Tone

Every claim in Act 5 and Act 6 is a claim about being wrong. Play those
straight — not self-deprecating, not triumphant. The retractions are the most
credible thing in the video, and hamming them up makes them read as a bit.
