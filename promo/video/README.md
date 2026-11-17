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

## Needs

- **Blender 4.2 – 4.5** (4.5 LTS recommended) on `PATH`, or `BLENDER=/path/to/blender`.
  Blender 5 removed an animation API the scene uses.
- `ffmpeg`, and `fonttools` + `brotli` for the system `python3` (the brand font
  ships as woff2 and Blender wants a TTF).

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
