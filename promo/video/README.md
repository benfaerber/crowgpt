# The CrowGPT film

A 21-second 3D animation, built entirely by a Python script inside Blender:
nothing is modelled by hand and there is no `.blend` file to keep.

    make -C promo video-stills   # six frames, to check framing
    make -C promo video          # 960x540 draft
    make -C promo video-final    # 1920x1080

Output goes to `data/video/` (gitignored): `crowgpt-film-<quality>.mp4`, the
frames beside it, and `work/blender.log`.

## What happens in it

| Seconds | Shot |
|---|---|
| 0 – 3.2 | A crow on a power line at dusk caws. The beak opens by the loudness of `real-alarm-call.wav`, frame by frame. |
| 3.2 – 11.3 | The call becomes a spectrogram (the clip's real one), lifts off as tokens, crosses the model, and seeds a second spectrogram that builds in time with `crowgpt2-preview.wav`. |
| 11.3 – 13.8 | A crow made of light gives the generated call. |
| 13.8 – 21 | The real crow listens, a flock crosses, the wordmark arrives. |

Both sounds are the ones the promo page already plays. The cut frames live in
`film/timeline.py`, and the soundtrack mix reads the same numbers, so moving a
cut moves the audio with it.

## The explainer

`make -C promo video-explainer` (`QUALITY=final` for 1080p) renders a second,
film along the same power line, with captions pinned to the lens. Its chapters
are written at 93 seconds and `ExplainerTimeline.PACE` (1.25) stretches them to
116 so a narrator has room; the table below is in unstretched seconds, and the
crow calls stay at their real speed. `QUALITY=preview` renders it with EEVEE at
540p in minutes, for timing a narration while the final renders.
Its job is to send people to crowgpt.org: it states the hypothesis the project
is testing and what a visitor's own recordings would add.

| Seconds | Chapter |
|---|---|
| 0 – 13 | The five backyard crows, and the goal: crow, human, crow. |
| 13 – 23 | A real call, its spectrogram, and the call types CawDex sorts it into. |
| 23 – 28 | An alarm at what? A type is not a meaning. |
| 28 – 46 | The hypothesis: a threat on the ground (a dog) and one in the air (a hawk) get different calls. Calls tagged `dog visible` and `raptor overhead` either land in separate groups or they do not. |
| 46 – 53 | That is one hypothesis: calls under other tags (`cat visible`, `human gives food`, `stranger approaching`) join the chart, one test at a time. |
| 53 – 61 | The field app, which records call and tag together. |
| 61 – 71 | CrowGPT: a call type in, a generated call out. |
| 71 – 83 | crowgpt.org's scan page: drop a file, get a labelled timeline, share it. |
| 83 – 93 | Nothing translated yet; the family under the wordmark; "Scan yours at crowgpt.org." |

The hypothesis chapter draws the outcome that would support it, under a
caption that begins "If": it is an illustration of the test, not a result.
The one number quoted (minutes of human-labelled audio) is read from
`promo/stats.json` at render time. Chapters live in `film/explainer.py`, the
props in `film/props.py`, the cut frames in `ExplainerTimeline`.

## The feature

`make -C promo video-feature` renders a third film, about six minutes, for
people who have never heard of the project: one crow's call nobody can read,
the five birds it started with, why crows are worth it, the five call types
with a clip of each, what CawDex got wrong and why, the animals known to name
their predators, the hypothesis, the app, CrowGPT, and the ask.

It is written to be narrated, and it is timed from the narration.
`film/screenplay.py` is the script: each line lasts as long as it takes to say
(2.5 words a second, plus a breath, plus any silence the picture needs), and
every scene in `film/feature.py` asks the screenplay when its lines are
spoken. Rewrite a line and the cuts, the captions and the sound cues all move.
`make -C promo video-feature-script` prints the script with the time each line
starts, to read from while recording.

`--scratch-voice` narrates the film with a synthetic voice, so the timing can
be heard before anyone records it, and prints every line that took the voice
longer than the screenplay allows. By default it is a clone of the narrator
made by Chatterbox from `--voice-of` (the explainer's narration unless told
otherwise): it needs the GPU for a few minutes, and its environment and
weights are fetched once into `data/video/work/voices`. `--scratch-voice piper`
is a stock voice that runs on the CPU. Neither is the voice of a finished film.

`--blend` writes the scene and its soundtrack to `data/video/crowgpt-feature.blend`
to scrub and play in Blender without rendering. The photographs in the film
(the family, the field kit) are the promo page's own, cropped by
`FeatureTimeline.PHOTOS`.

Its claims are the promo page's own or published findings: the figures come
from `promo/stats.json` at render time, the hypothesis chapter says the chart
is what a yes would look like and not a result, and the two archive clips it
plays carry their Xeno-canto credit on screen.

`--shape square` and `--shape tall` (9:16, for phones) keep the wide picture's
width and add sky above and ground below; the tall cut re-wraps the captions
larger into the ground under the picture.

`--device gpu` renders on the card (OptiX, then CUDA) and falls back to the CPU
if Cycles cannot see one. Read `GPU-CALENDAR.md` first.

## The owl film

`make -C promo video-owl` renders a standalone film, about three and a half
minutes, on one question: crows mobbing an owl sound different from crows
mobbing a hawk, so are they naming the predator? It follows experiments 0102
to 0113: the archive result (0.78), its replication on new recordings
(0.75), and the three suspects (a call that means owl, posture, the crowd),
each with what its test found. It ends where they do, with a difference that is
real and no evidence yet of a name, and asks for a recording of a perched hawk
being mobbed.

It is timed from its narration like the feature (`film/owl_screenplay.py`,
`make -C promo video-owl-script`) and its scenes are methods of a `Feature`
subclass in `film/owl.py`, so any of them can move into the feature unchanged.
Every figure is written into the screenplay from the experiment READMEs, not
from `promo/stats.json`. The crows heard are the family's own alarm calls, not
an owl or hawk mob: the picture says what is being mobbed, the sound does not.

## Needs

- **Blender**, tested on 5.2 LTS. `render.py` looks for `blender` on `PATH`, then
  for the Flatpak (`org.blender.Blender`); `BLENDER='...'` or `--blender` names
  another. A Flatpak Blender cannot see `/tmp`, which is one reason everything
  is written under `data/video/`.
- `ffmpeg`, and `fonttools` + `brotli` in `/usr/bin/python3`, which the make
  targets use (the brand font ships as woff2 and Blender wants a TTF).

It renders with Cycles on the CPU, 24 threads by default (`--threads`), and
never touches the GPU. Progress reports through `crowgpt.progress.Run`, so a
render has a card on the dashboard's Training panel. A stopped render resumes:
frames already on disk are skipped unless `--fresh` is passed.

## Layout

- `render.py` — prepares audio and font, runs Blender, mixes the soundtrack, encodes.
- `scene.py` — what Blender runs.
- `film/director.py` — the shot list and render settings.
- `film/sets.py`, `film/crow.py` — the sets and the cast.
- `film/audio.py` — loudness per frame and the spectrogram, from the wav.
- `film/kit.py` — palette (the promo's dusk theme), materials, shapes, keyframes.
