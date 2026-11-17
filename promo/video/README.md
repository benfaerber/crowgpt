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
92-second film along the same power line, with captions pinned to the lens.
Its job is to send people to crowgpt.org: it states the hypothesis the project
is testing and what a visitor's own recordings would add.

| Seconds | Chapter |
|---|---|
| 0 – 13 | The five backyard crows, and the goal: crow, human, crow. |
| 13 – 23 | A real call, its spectrogram, and the call types CawDex sorts it into. |
| 23 – 28 | An alarm at what? A type is not a meaning. |
| 28 – 46 | The hypothesis: a threat on the ground (a dog) and one in the air (a hawk) get different calls. Calls tagged `dog visible` and `raptor overhead` either land in separate groups or they do not. |
| 46 – 60 | The field app, which records call and tag together, and CawScout. |
| 60 – 70 | CrowGPT: a call type in, a generated call out. |
| 70 – 82 | crowgpt.org's scan page: drop a file, get a labelled timeline, share it. |
| 82 – 92 | Nothing translated yet; the family under the wordmark; "Scan yours at crowgpt.org." |

The hypothesis chapter draws the outcome that would support it, under a
caption that begins "If": it is an illustration of the test, not a result.
The one number quoted (minutes of human-labelled audio) is read from
`promo/stats.json` at render time. Chapters live in `film/explainer.py`, the
props in `film/props.py`, the cut frames in `ExplainerTimeline`.

`--device gpu` renders on the card (OptiX, then CUDA) and falls back to the CPU
if Cycles cannot see one. Read `GPU-CALENDAR.md` first.

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
