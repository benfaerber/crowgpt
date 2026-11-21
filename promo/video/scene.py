"""Blender's entry point: blender -b --python scene.py -- --work DIR --frames DIR ...

Run it through render.py, which prepares the audio and the font first.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from film.director import Darkroom, Film  # noqa: E402
from film.explainer import Explainer  # noqa: E402
from film.feature import Feature  # noqa: E402

FILMS = {"short": Film, "explainer": Explainer, "feature": Feature}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--logo", required=True)
    parser.add_argument("--quality", default="draft")
    parser.add_argument("--threads", type=int, default=24)
    parser.add_argument("--stills", default="")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--film", choices=sorted(FILMS), default="short")
    parser.add_argument("--stats", default="")
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--save", default="")
    parser.add_argument("--shape", choices=("wide", "square", "tall"), default="wide")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])

    film = FILMS[options.film](options.work, options.logo, options.stats, options.shape)
    scene = film.build()
    darkroom = Darkroom(scene, options.quality, options.threads, options.device, options.shape)
    if options.save:
        import bpy
        bpy.ops.wm.save_as_mainfile(filepath=options.save)
    if options.stills:
        darkroom.stills([int(frame) for frame in options.stills.split(",")], options.frames)
    else:
        darkroom.animation(options.frames, options.start, options.end or film.CLOCK.length())


main()
