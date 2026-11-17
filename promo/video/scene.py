"""Blender's entry point: blender -b --python scene.py -- --work DIR --frames DIR ...

Run it through render.py, which prepares the audio and the font first.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from film.director import Darkroom, Film  # noqa: E402
from film.timeline import Timeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--logo", required=True)
    parser.add_argument("--quality", default="draft")
    parser.add_argument("--threads", type=int, default=24)
    parser.add_argument("--stills", default="")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=Timeline.END)
    parser.add_argument("--save", default="")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])

    scene = Film(options.work, options.logo).build()
    darkroom = Darkroom(scene, options.quality, options.threads)
    if options.save:
        import bpy
        bpy.ops.wm.save_as_mainfile(filepath=options.save)
    if options.stills:
        darkroom.stills([int(frame) for frame in options.stills.split(",")], options.frames)
    else:
        darkroom.animation(options.frames, options.start, options.end)


main()
